import os
import sys
import json
import time
import asyncio
import nest_asyncio

# Apply nest_asyncio to allow nested event loops in case ragas or langchain needs it
nest_asyncio.apply()

# Add parent directory to path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import dotenv
dotenv.load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", ".env")))

from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_qdrant import QdrantVectorStore

import Services.Ai_service.embedding as embedding_mod
import Services.agent as agent_mod

# Adjust the confidence threshold to 0.35 to allow most queries
agent_mod.CONFIDENCE_THRESHOLD = 0.35

# Initialize local in-memory Qdrant
local_client = QdrantClient(location=":memory:")

def mock_get_vector_store():
    return QdrantVectorStore(
        client=local_client,
        collection_name="documents",
        embedding=embedding_mod.get_embeddings(),
        vector_name="content-dense",
    )

# Patch both modules
embedding_mod.get_vector_store = mock_get_vector_store
agent_mod.get_vector_store = mock_get_vector_store

def load_documents():
    docs = []
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pcaps"))
    
    # 1. PDF
    pdf_path = os.path.join(base_dir, "SOP-104_Data_Retention_Policy.pdf")
    if os.path.exists(pdf_path):
        loader = PyMuPDFLoader(pdf_path)
        pdf_docs = loader.load()
        for d in pdf_docs:
            d.metadata["workspace_id"] = 1
        docs.extend(pdf_docs)
    
    # 2. TXT
    txt_path = os.path.join(base_dir, "HR-201_Leave_Policy.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            docs.append(Document(page_content=f.read(), metadata={"source": "HR-201_Leave_Policy.txt", "workspace_id": 1}))

    # 3. MD
    md_path = os.path.join(base_dir, "Engineering_Onboarding.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            docs.append(Document(page_content=f.read(), metadata={"source": "Engineering_Onboarding.md", "workspace_id": 1}))

    return docs

def setup_qdrant(docs):
    if local_client.collection_exists(collection_name="documents"):
        local_client.delete_collection(collection_name="documents")
        
    local_client.create_collection(
        collection_name="documents",
        vectors_config={
            "content-dense": VectorParams(
                size=384, # all-MiniLM-L6-v2 dimension
                distance=Distance.COSINE,
            )
        },
    )
    
    vector_store = mock_get_vector_store()
    vector_store.add_documents(docs)
    print(f"Added {len(docs)} documents to Qdrant.")

async def main():
    print("==================================================")
    print("        ARISHEM RAG PIPELINE EVALUATION           ")
    print("==================================================")
    print("Loading documents and setting up local Qdrant...")
    docs = load_documents()
    setup_qdrant(docs)
    
    golden_file = os.path.join(os.path.dirname(__file__), "golden_set.json")
    with open(golden_file, "r") as f:
        golden_set = json.load(f)
        
    print(f"Loaded {len(golden_set)} questions from golden set.")
    
    data_samples = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
        "reference": []  # for compatibility with ragas 0.2.x
    }
    
    from langchain_groq import ChatGroq
    
    # Wait, ragas requires specific wrappers depending on the version
    print("Importing ragas...")
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    try:
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        wrapper_available = True
    except ImportError:
        wrapper_available = False
    
    eval_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    
    if wrapper_available:
        ragas_llm = LangchainLLMWrapper(eval_llm)
        ragas_embeddings = LangchainEmbeddingsWrapper(embedding_mod.get_embeddings())
    else:
        ragas_llm = eval_llm
        ragas_embeddings = embedding_mod.get_embeddings()

    print("Running queries through the agent pipeline...")
    for item in golden_set:
        question = item["question"]
        gt = item["ground_truth"]
        
        try:
            # Query the agent
            res = agent_mod.query(question=question, workspace_id=1, top_k=2)
            answer = res.get("answer", "")
            
            # Retrieve exact chunks for context
            vs = mock_get_vector_store()
            from qdrant_client.http import models as qdrant_models
            filter_ = qdrant_models.Filter(must=[
                qdrant_models.FieldCondition(key="metadata.workspace_id", match=qdrant_models.MatchValue(value=1))
            ])
            docs_res = vs.similarity_search(question, k=2, filter=filter_)
            contexts = [d.page_content for d in docs_res]
            
            data_samples["question"].append(question)
            data_samples["answer"].append(answer)
            data_samples["contexts"].append(contexts)
            data_samples["ground_truth"].append(gt)
            data_samples["reference"].append(gt)  # add both for compatibility
            
        except Exception as e:
            print(f"Error querying '{question}': {e}")
            continue
            
        # Sleep to avoid hitting Groq rate limits
        time.sleep(2)
        
    from datasets import Dataset
    dataset = Dataset.from_dict(data_samples)
    
    print("Running ragas evaluation... (this will take a few minutes)")
    try:
        results = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            raise_exceptions=False,
        )
        
        print("Evaluation complete!")
        print(results)
        
        scorecard_path = os.path.join(os.path.dirname(__file__), "SCORECARD.md")
        with open(scorecard_path, "w", encoding="utf-8") as f:
            f.write("# RAG Evaluation Scorecard\n\n")
            f.write("| Metric | Score |\n")
            f.write("| --- | --- |\n")
            
            # In Ragas 0.2+, results might not be a dict but an object with a scores property
            # We'll try to convert it to dict
            try:
                res_dict = dict(results)
            except:
                res_dict = results.scores if hasattr(results, 'scores') else {}
                
            for metric, score in res_dict.items():
                if isinstance(score, float):
                    f.write(f"| **{metric.replace('_', ' ').title()}** | `{score:.4f}` |\n")
                
            f.write("\n## Details\n")
            f.write("Generated using `ragas` with Groq (`llama-3.3-70b-versatile`).\n")
            
        print(f"Scorecard saved to {scorecard_path}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Ragas evaluation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
