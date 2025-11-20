"""
RAG (Retrieval-Augmented Generation) Database module for game information storage and retrieval.
"""
import os
from typing import List, Dict, Any
from pathlib import Path
import logging

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain.schema import Document
except ImportError:
    # Fallback for testing without langchain
    logging.warning("LangChain not installed. RAG functionality will be limited.")

logger = logging.getLogger(__name__)


class RAGDatabase:
    """RAG Database for storing and retrieving game information."""
    
    def __init__(
        self,
        data_path: str = "data/game_info",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """
        Initialize the RAG Database.
        
        Args:
            data_path: Path to directory containing game information files
            embedding_model: HuggingFace embedding model name
            chunk_size: Size of text chunks for splitting
            chunk_overlap: Overlap between chunks
        """
        self.data_path = Path(data_path)
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.vectorstore = None
        self.embeddings = None
        
        logger.info(f"Initializing RAG Database with data path: {data_path}")
        
        # Create data directory if it doesn't exist
        self.data_path.mkdir(parents=True, exist_ok=True)
    
    def load_embeddings(self):
        """Load the embedding model."""
        if self.embeddings is None:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self.embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                model_kwargs={'device': 'cpu'}
            )
            logger.info("Embedding model loaded successfully")
    
    def load_documents(self) -> List[Document]:
        """
        Load documents from the data directory.
        
        Returns:
            List of Document objects
        """
        documents = []
        
        # Load text files from data directory
        for file_path in self.data_path.glob("*.txt"):
            logger.info(f"Loading document: {file_path.name}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                documents.append(Document(
                    page_content=content,
                    metadata={"source": file_path.name}
                ))
        
        logger.info(f"Loaded {len(documents)} documents")
        return documents
    
    def initialize_vectorstore(self, force_reload: bool = False):
        """
        Initialize or reload the vector store.
        
        Args:
            force_reload: Force reload even if vectorstore exists
        """
        if self.vectorstore is not None and not force_reload:
            logger.info("Vector store already initialized")
            return
        
        self.load_embeddings()
        
        # Load and split documents
        documents = self.load_documents()
        
        if not documents:
            logger.warning("No documents found. Creating empty vector store.")
            documents = [Document(
                page_content="No game information available yet.",
                metadata={"source": "default"}
            )]
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        splits = text_splitter.split_documents(documents)
        logger.info(f"Split documents into {len(splits)} chunks")
        
        # Create vector store
        logger.info("Creating vector store...")
        self.vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=self.embeddings,
            persist_directory=str(self.data_path / "chroma_db")
        )
        logger.info("Vector store initialized successfully")
    
    def query(self, query_text: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Query the RAG database for relevant information.
        
        Args:
            query_text: Query string
            k: Number of top results to return
            
        Returns:
            List of dictionaries containing relevant documents and metadata
        """
        if self.vectorstore is None:
            self.initialize_vectorstore()
        
        logger.info(f"Querying RAG database: '{query_text}'")
        results = self.vectorstore.similarity_search(query_text, k=k)
        
        formatted_results = []
        for doc in results:
            formatted_results.append({
                "content": doc.page_content,
                "metadata": doc.metadata
            })
        
        logger.info(f"Retrieved {len(formatted_results)} relevant documents")
        return formatted_results
    
    def get_context(self, query_text: str, k: int = 3) -> str:
        """
        Get context string from relevant documents for LLM.
        
        Args:
            query_text: Query string
            k: Number of top results to retrieve
            
        Returns:
            Formatted context string
        """
        results = self.query(query_text, k)
        
        if not results:
            return "No relevant game information found."
        
        context_parts = []
        for i, result in enumerate(results, 1):
            source = result["metadata"].get("source", "unknown")
            content = result["content"]
            context_parts.append(f"[Source {i}: {source}]\n{content}")
        
        return "\n\n".join(context_parts)
