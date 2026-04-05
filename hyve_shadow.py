"""
HYVE Component: Shadow Dreamer
================================
Autonomous self-improvement during idle time.
Analyzes worst-performing interactions, generates improvement hypotheses,
and queues them for execution and validation.

Lineage: Shadow_Nox_Dreamer.py → Left_Brain_Daemon.py → HYVE Shadow Dreamer

NOTE: This module does NOT execute code autonomously.
It generates improvement proposals that require human approval.
The autonomous execution loop (Left_Brain_Daemon) can be enabled 
separately for sandboxed environments.
"""

import os
import json
import time
import datetime
import threading


SHADOW_QUEUE_PATH = "nexus_shadow_queue.json"
SHADOW_LOG_PATH = "nexus_shadow_log.json"


class ShadowDreamer:
    """
    During idle time, analyzes conversation history to identify:
    1. Knowledge gaps (topics where spatial retrieval returned few hits)
    2. Quality failures (low auditor scores)
    3. Repetitive patterns (topics that keep recurring without resolution)
    
    Generates structured improvement proposals:
    - Research tasks (topics to study)
    - Skill gaps (LoRA adapters to train)
    - Memory gaps (regions of VALENCE geometry to fill)
    
    In autonomous mode (with Left_Brain_Daemon), can execute
    code mutations in a sandboxed environment and crystallize
    successful improvements as LoRA adapters.
    """
    
    def __init__(self, episodic_memory_ref, engram_store_ref):
        self.episodic_memory = episodic_memory_ref
        self.engram_store = engram_store_ref
        self.queue = self._load_queue()
        self.log = self._load_log()
        self.frustration_counter = 0
        self.frustration_threshold = 5
        self._running = True
        self._idle_thread = None
        self.last_activity = time.time()
        
        print(f"[HYVE::Shadow] Online. Pending improvements: {len(self.queue)}")
    
    def _load_queue(self):
        if os.path.exists(SHADOW_QUEUE_PATH):
            with open(SHADOW_QUEUE_PATH, "r") as f:
                return json.load(f)
        return []
    
    def _load_log(self):
        if os.path.exists(SHADOW_LOG_PATH):
            with open(SHADOW_LOG_PATH, "r") as f:
                return json.load(f)
        return []
    
    def save(self):
        with open(SHADOW_QUEUE_PATH, "w") as f:
            json.dump(self.queue, f, indent=2)
        with open(SHADOW_LOG_PATH, "w") as f:
            json.dump(self.log[-1000:], f, indent=2)  # Keep last 1000 entries
    
    def wake(self):
        """Signal that user activity occurred."""
        self.last_activity = time.time()
    
    def start(self):
        """Start the background analysis thread."""
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()
    
    def stop(self):
        self._running = False
        if self._idle_thread:
            self._idle_thread.join(timeout=2.0)
        self.save()
    
    def _idle_loop(self):
        """Background loop that runs analysis during idle time."""
        analysis_interval = 120  # Analyze every 2 minutes of idle time
        last_analysis = 0
        
        while self._running:
            idle_time = time.time() - self.last_activity
            
            if idle_time > 60.0 and (time.time() - last_analysis) > analysis_interval:
                self._analyze_and_propose()
                last_analysis = time.time()
            
            time.sleep(5.0)
    
    def _analyze_and_propose(self):
        """
        Core analysis loop. Examines recent episodic memory
        and generates improvement proposals.
        """
        if not self.episodic_memory:
            return
        
        recent = self.episodic_memory[-50:]  # Last 50 interactions
        
        # === ANALYSIS 1: Low quality episodes ===
        low_quality = [ep for ep in recent if ep.get("weight", 1.0) < 0.3]
        if low_quality:
            # Extract common keywords from failed interactions
            all_keywords = []
            for ep in low_quality:
                all_keywords.extend(ep.get("keywords", []))
            
            if all_keywords:
                from collections import Counter
                common_failures = Counter(all_keywords).most_common(5)
                
                for keyword, count in common_failures:
                    if count >= 2:  # Same topic failed multiple times
                        proposal = {
                            "type": "knowledge_gap",
                            "topic": keyword,
                            "evidence": f"Failed {count} times in recent {len(recent)} interactions",
                            "proposed_action": f"Research '{keyword}' and store findings in semantic engrams",
                            "priority": min(1.0, count / 5.0),
                            "timestamp": datetime.datetime.now().isoformat(),
                            "status": "pending"
                        }
                        
                        # Don't duplicate existing proposals
                        existing_topics = {p["topic"] for p in self.queue if p["type"] == "knowledge_gap"}
                        if keyword not in existing_topics:
                            self.queue.append(proposal)
                            print(f"\r  [Shadow] Identified knowledge gap: '{keyword}' (failed {count}x)", 
                                  end="", flush=True)
        
        # === ANALYSIS 2: Repetitive topics without resolution ===
        all_recent_keywords = []
        for ep in recent:
            all_recent_keywords.extend(ep.get("keywords", []))
        
        from collections import Counter
        topic_freq = Counter(all_recent_keywords)
        repetitive = [(topic, count) for topic, count in topic_freq.most_common(10) if count > 5]
        
        for topic, count in repetitive:
            proposal = {
                "type": "repetitive_pattern",
                "topic": topic,
                "evidence": f"Appeared {count} times in last {len(recent)} interactions",
                "proposed_action": f"Develop deeper expertise on '{topic}' — possibly train a specialized LoRA",
                "priority": min(1.0, count / 10.0),
                "timestamp": datetime.datetime.now().isoformat(),
                "status": "pending"
            }
            
            existing = {p["topic"] for p in self.queue if p["type"] == "repetitive_pattern"}
            if topic not in existing:
                self.queue.append(proposal)
        
        # === ANALYSIS 3: Inner state stagnation ===
        inner_snapshots = [ep.get("inner_state_snapshot", {}) for ep in recent if ep.get("inner_state_snapshot")]
        if inner_snapshots:
            # Check if the same states dominate every interaction
            state_freq = Counter()
            for snap in inner_snapshots:
                for state, activation in snap.items():
                    if activation > 0.3:
                        state_freq[state] += 1
            
            total = len(inner_snapshots)
            for state, count in state_freq.most_common(3):
                if count / total > 0.8:  # Same state active in >80% of interactions
                    proposal = {
                        "type": "emotional_stagnation",
                        "topic": state,
                        "evidence": f"State '{state}' active in {count}/{total} recent interactions",
                        "proposed_action": f"Seek novelty — current conversations are emotionally monotone",
                        "priority": 0.3,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "status": "pending"
                    }
                    self.queue.append(proposal)
        
        # Trim queue to prevent unbounded growth
        self.queue = self.queue[-100:]
        self.save()
    
    def get_pending_proposals(self, max_count=5):
        """Get proposals for display or execution."""
        pending = [p for p in self.queue if p["status"] == "pending"]
        pending.sort(key=lambda x: x["priority"], reverse=True)
        return pending[:max_count]
    
    def resolve_proposal(self, index, status="completed", notes=""):
        """Mark a proposal as completed or dismissed."""
        if 0 <= index < len(self.queue):
            self.queue[index]["status"] = status
            self.queue[index]["resolved_at"] = datetime.datetime.now().isoformat()
            self.queue[index]["notes"] = notes
            
            self.log.append(self.queue[index])
            self.save()
