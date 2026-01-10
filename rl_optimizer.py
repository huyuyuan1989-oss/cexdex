
import json
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class RLOptimizer:
    """
    V7 RL Core: Reinforcement Learning Optimizer (自我進化模組)
    
    Function:
    1. Read 'paper_trades.json' (History)
    2. Read 'agent_config.json' (Current Policy)
    3. Calculate Win Rate & PnL derived from each agent type (implicitly)
    4. Adjust Agent Weights:
       - If LONGs are losing in Bear Market -> Reduce Aggressor Weight, Increase Skeptic Weight
       - If SHORTs are losing in Bull Market -> Reduce Skeptic Weight
    """
    
    def __init__(self):
        self.report_dir = Path(__file__).parent / "reports"
        self.trades_file = self.report_dir / "paper_trades.json"
        self.config_file = self.report_dir / "agent_config.json"
        
        # Default Weights
        self.default_weights = {
            "Momentum": 1.0,    # Aggressor
            "Risk Control": 1.0,# Skeptic
            "Smart Money": 1.0  # Sage
        }

    def run_optimization(self):
        """
        Main entry point for RL Optimization
        """
        logger.info("🧠 V7 RL Core: Starting Policy Optimization...")
        
        trades = self._load_trades()
        if not trades:
            logger.info("   ⚠ No trade history found. Skipping optimization.")
            return

        # 1. Analyze Performance
        closed_trades = [t for t in trades if t['status'] != 'OPEN']
        if len(closed_trades) < 5:
            logger.info("   ⚠ Not enough closed trades (<5) for statistical significance.")
            return

        win_trades = [t for t in closed_trades if t.get('pnl_pct', 0) > 0]
        loss_trades = [t for t in closed_trades if t.get('pnl_pct', 0) <= 0]
        
        win_rate = len(win_trades) / len(closed_trades)
        avg_pnl = sum([t.get('pnl_pct', 0) for t in closed_trades]) / len(closed_trades)
        
        logger.info(f"   📊 Performance: Win Rate {win_rate*100:.1f}%, Avg PnL {avg_pnl:.2f}%")

        # 2. Logic for Weight Adjustment (Simplified Q-Learning Concept)
        # Identify "Market Regime" based on recent trades
        # If we are losing money on LONGs -> Market is Bearish -> Boost Skeptic
        # If we are losing money on SHORTs -> Market is Bullish -> Boost Aggressor
        
        long_losses = [t for t in loss_trades if t['direction'] == 'LONG']
        short_losses = [t for t in loss_trades if t['direction'] == 'SHORT']
        
        current_config = self._load_config()
        weights = current_config.get('weights', self.default_weights)
        
        # Learning Rate
        alpha = 0.1 
        
        # Scenario A: Longs are failing (Aggressor is too bullish)
        if len(long_losses) > len(short_losses):
            logger.info("   📉 Detected weakness in LONG strategies. Reducing Momentum weight.")
            weights['Momentum'] = max(0.5, weights['Momentum'] - alpha)
            weights['Risk Control'] = min(2.0, weights['Risk Control'] + alpha)
            
        # Scenario B: Shorts are failing (Skeptic is too bearish)
        elif len(short_losses) > len(long_losses):
            logger.info("   📈 Detected weakness in SHORT strategies. Reducing Risk Control weight.")
            weights['Risk Control'] = max(0.5, weights['Risk Control'] - alpha)
            weights['Momentum'] = min(2.0, weights['Momentum'] + alpha)
            
        # Scenario C: Stable / Sage is Key (Smart Money usually reliable)
        # We slightly boost Sage if overall winrate is high
        if win_rate > 0.6:
            weights['Smart Money'] = min(1.5, weights['Smart Money'] + 0.05)
            
        # 3. Save New Policy
        new_config = {
            "updated_at": datetime.now().isoformat(),
            "weights": weights,
            "stats": {
                "total_trades": len(closed_trades),
                "win_rate": round(win_rate * 100, 1),
                "avg_pnl": round(avg_pnl, 2)
            }
        }
        
        self._save_config(new_config)
        logger.info(f"   ✅ Policy Updated: {weights}")

    def _load_trades(self) -> List[Dict]:
        if self.trades_file.exists():
            try:
                with open(self.trades_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _load_config(self) -> Dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_config(self, config: Dict):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rl = RLOptimizer()
    rl.run_optimization()
