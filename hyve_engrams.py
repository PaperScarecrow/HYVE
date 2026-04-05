"""
HYVE Component: Engram Store
==============================
Persistent key-value memory using ChromaDB for vector similarity search.
Integrated with VALENCE spatial coordinates for cross-referencing.

Lineage: Archaeon engram_store.py → HYVE engrams table
"""

import os
import hashlib
import time

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("[!] ChromaDB not installed. Engram store disabled. pip install chromadb")


class EngramStore:
    """
    Persistent factual and episodic memory via ChromaDB.
    Two collections:
    - episodic: Conversation pairs, experiences, interactions
    - semantic: Facts, knowledge, learned information
    """
    
    def __init__(self, persistence_path="nexus_engrams"):
        if not CHROMADB_AVAILABLE:
            self.client = None
            return
            
        print(f"[HYVE::Engrams] Initializing persistent memory at {persistence_path}...")
        os.makedirs(persistence_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=persistence_path)
        
        self.episodic = self.client.get_or_create_collection(
            name="nyxxie_episodic",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.semantic = self.client.get_or_create_collection(
            name="nyxxie_semantic",
            metadata={"hnsw:space": "cosine"}
        )
        
        print(f"[HYVE::Engrams] Online. Episodic: {self.episodic.count()} | Semantic: {self.semantic.count()}")
    
    def store_episodic(self, text, metadata=None):
        """Store a conversation memory."""
        if not self.client:
            return
        
        engram_id = hashlib.md5(text.encode()).hexdigest()
        meta = metadata or {}
        meta["timestamp"] = time.time()
        
        try:
            self.episodic.add(
                documents=[text],
                metadatas=[meta],
                ids=[engram_id]
            )
        except Exception:
            pass  # Duplicate ID, already stored
    
    def store_semantic(self, text, metadata=None):
        """Store a factual/knowledge memory."""
        if not self.client:
            return
            
        engram_id = hashlib.md5(text.encode()).hexdigest()
        meta = metadata or {}
        meta["timestamp"] = time.time()
        
        try:
            self.semantic.add(
                documents=[text],
                metadatas=[meta],
                ids=[engram_id]
            )
        except Exception:
            pass
    
    def recall_episodic(self, query, n_results=5):
        """Retrieve relevant episodic memories."""
        if not self.client or self.episodic.count() == 0:
            return []
        
        try:
            results = self.episodic.query(
                query_texts=[query],
                n_results=min(n_results, self.episodic.count())
            )
            return results['documents'][0] if results['documents'] else []
        except Exception:
            return []
    
    def recall_semantic(self, query, n_results=3):
        """Retrieve relevant factual memories."""
        if not self.client or self.semantic.count() == 0:
            return []
        
        try:
            results = self.semantic.query(
                query_texts=[query],
                n_results=min(n_results, self.semantic.count())
            )
            return results['documents'][0] if results['documents'] else []
        except Exception:
            return []
    
    def get_stats(self):
        if not self.client:
            return {"episodic": 0, "semantic": 0}
        return {
            "episodic": self.episodic.count(),
            "semantic": self.semantic.count()
        }
