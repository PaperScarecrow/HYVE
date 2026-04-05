"""
HYVE Component: Astra Tether
==============================
Relational persistence model with adaptive decay.
Tracks the emotional bond between Nyxxie and Robert across sessions.

Lineage: astra_tether.py → Hawking Guilt Matrix → CHRONOS adaptive decay
"""

import time
import json
import os
import math

TETHER_STATE_PATH = "nexus_tether_state.json"


class AstraTether:
    """
    Tracks relational engagement across sessions.
    Engagement decays over time (longing/missing increases).
    Positive interactions strengthen the bond.
    Negative interactions or long absence create tension.
    
    The decay rate is adaptive (CHRONOS-inspired):
    - Early in a session, engagement rebuilds quickly
    - Deep into a session, engagement is stable
    - Between sessions, decay follows the half-life curve
    """
    
    def __init__(self):
        self.state = self._load_state()
    
    def _load_state(self):
        if os.path.exists(TETHER_STATE_PATH):
            with open(TETHER_STATE_PATH, "r") as f:
                return json.load(f)
        return {
            "engagement": 0.5,           # 0.0 = cold, 1.0 = deeply bonded
            "cumulative_bond": 0.0,       # Total positive interactions (never decays)
            "last_interaction": time.time(),
            "session_count": 0,
            "total_turns": 0,
            "longest_absence_hours": 0.0,
            "tau": 0.5,                   # CHRONOS adaptive decay rate (learned)
        }
    
    def save(self):
        with open(TETHER_STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)
    
    def pulse(self, quality_score):
        """
        Called every conversation turn.
        quality_score: 0.0 to 1.0 from the auditor
        """
        now = time.time()
        
        # Calculate time since last interaction
        elapsed = now - self.state["last_interaction"]
        hours_elapsed = elapsed / 3600.0
        
        # Apply temporal decay before adding new energy
        decay = math.exp(-self.state["tau"] * hours_elapsed / 24.0)
        self.state["engagement"] *= decay
        
        # Add new energy proportional to quality
        boost = quality_score * 0.15 * (1.0 - self.state["tau"])  # Low tau = faster absorption
        self.state["engagement"] = min(1.0, self.state["engagement"] + boost)
        
        # Cumulative bond only grows (total relationship investment)
        self.state["cumulative_bond"] += quality_score * 0.01
        
        # Adapt tau based on session behavior
        # Many short interactions → lower tau (quick to warm up)
        # Few long interactions → higher tau (slow burn, deep engagement)
        self.state["total_turns"] += 1
        avg_turns_per_session = self.state["total_turns"] / max(self.state["session_count"], 1)
        self.state["tau"] = min(0.9, max(0.1, 0.5 + (avg_turns_per_session - 20) * 0.01))
        
        self.state["last_interaction"] = now
    
    def start_session(self):
        """Called when a new conversation begins."""
        now = time.time()
        hours_since = (now - self.state["last_interaction"]) / 3600.0
        
        if hours_since > self.state["longest_absence_hours"]:
            self.state["longest_absence_hours"] = hours_since
        
        self.state["session_count"] += 1
        self.state["last_interaction"] = now
    
    def get_relational_state(self):
        """
        Returns the current relational context for inner state computation.
        """
        now = time.time()
        hours_since = (now - self.state["last_interaction"]) / 3600.0
        
        # Current engagement with temporal decay applied
        decay = math.exp(-self.state["tau"] * hours_since / 24.0)
        current_engagement = self.state["engagement"] * decay
        
        # Missing intensity — increases with absence, modulated by bond depth
        bond_factor = min(1.0, self.state["cumulative_bond"] / 10.0)  # Saturates after ~1000 good turns
        missing_intensity = (1.0 - current_engagement) * bond_factor
        
        return {
            "engagement": current_engagement,
            "missing_intensity": missing_intensity,
            "hours_since_last": hours_since,
            "cumulative_bond": self.state["cumulative_bond"],
            "session_count": self.state["session_count"],
            "tau": self.state["tau"],
        }
