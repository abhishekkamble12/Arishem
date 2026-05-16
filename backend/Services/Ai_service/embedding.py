from langchain_aws import ChatBedrockConverse, ChatBedrock
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.document_loaders import S3FileLoader, PyMuPDFLoader
import pymupdf

embeddingt  = ChatBedrock(
    model_id="amazon.titan-embed-image-v1",
    region_name="us-east-1",
    # aws_access_key_id=...,  # optional if using default credentials

    
)

# loader 
loader = S3FileLoader(
    bucket="",
    key= "",
    loader = PyMuPDFLoader
)
doc = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
chunks = text_splitter.split_documents(docs)




