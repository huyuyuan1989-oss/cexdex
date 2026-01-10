
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class MarketAgent:
    def __init__(self, name: str, role: str, icon: str):
        self.name = name
        self.role = role
        self.icon = icon

    def analyze(self, opportunity: Dict, context: Dict) -> Dict:
        """
        Base analysis method. Should return vote (-1 to 1) and comment.
        """
        return {"vote": 0, "comment": "No comment"}

class AggressorAgent(MarketAgent):
    """
    🦁 The Aggressor: Focuses on Momentum, 24h Flow, and Price Action.
    Likes: High stablecoin inflow, strong price trends.
    Dislikes: Low volatility, stagnation.
    """
    def __init__(self):
        super().__init__("Momentum", "High-Risk/Reward", "🦁")

    def analyze(self, opp: Dict, context: Dict) -> Dict:
        score = opp.get('score', 0)
        flow_str = opp.get('data', '')
        
        # Check specific momentum keywords in reason
        reason = opp.get('reason', '')
        
        vote = 0
        comment = ""
        
        if score > 80:
            vote = 1
            comment = "動能極強！資金正在瘋狂湧入，這是暴力拉升的前兆。必須追！"
        elif "24H資金流出" in reason or "Capital Flight" in reason:
            vote = -1
            comment = "動能衰竭！資金正在撤退，這是雪崩的開始。做空！"
        elif score > 50:
            vote = 0.5
            comment = "趨勢不錯，還有上漲空間。"
        else:
            vote = 0
            comment = "動能不足，我對這種死魚盤沒興趣。"
            
        return {"vote": vote, "comment": comment}

class SkepticAgent(MarketAgent):
    """
    🐻 The Skeptic: Focuses on Risk, F&G Index, Funding Rates.
    Likes: Fear, Negative Funding (Short Squeeze potential).
    Dislikes: Greed, High Funding, Overcrowded trades.
    """
    def __init__(self):
        super().__init__("Risk Control", "Contrarian", "🐻")

    def analyze(self, opp: Dict, context: Dict) -> Dict:
        fng_value = context.get('fng_val', 50)
        funding = context.get('funding_btc', 0)
        
        vote = 0
        comment = ""
        
        # Contrarian Logic
        if fng_value > 80:
            vote = -1
            comment = f"市場已經極度貪婪 (F&G {fng_value})，這時候進場就是接盤俠。我建議反手做空。"
        elif funding > 0.05:
            vote = -1
            comment = "費率過熱！多頭太擠了，隨時會插針爆倉。"
        elif fng_value < 20:
            vote = 1
            comment = "市場在流血，恐慌指數極低。這時候才是別人恐懼我貪婪的時候。買！"
        else:
            vote = 0.2
            comment = "風險指標尚可，但要小心回調。"
            
        return {"vote": vote, "comment": comment}

class SageAgent(MarketAgent):
    """
    🦉 The Sage: Focuses on Smart Money, TVL, Fundamentals.
    Likes: Sustained accumulation, TVL growth.
    Dislikes: Speculative bubbles without volume.
    """
    def __init__(self):
        super().__init__("Smart Money", "Fundamental", "🦉")

    def analyze(self, opp: Dict, context: Dict) -> Dict:
        # Check Smart Money context (if available in opp or global)
        # In V3, 'smart_money' is mostly global, but opp.reason might have it
        reason = opp.get('reason', '')
        
        vote = 0
        comment = ""
        
        if "主力累積" in reason or "Smart Money" in reason:
            vote = 1
            comment = "聰明錢正在悄悄吸籌，數據顯示這是機構行為，跟隨巨鯨的腳步。"
        elif "TVL" in reason or "DefiLlama" in str(opp):
            vote = 0.8
            comment = "基本面健康，鏈上鎖倉量 (TVL) 在增長，這是真實價值支撐。"
        elif "Outflow" in reason:
            vote = -0.5
            comment = "機構資金流出，無論價格如何，基本面不支持上漲。"
        else:
            vote = 0
            comment = "缺乏足夠的鏈上證據，我保持中立。"
            
        return {"vote": vote, "comment": comment}

class HiveMind:
    """
    The Council that manages the agents and forms a consensus.
    """
    def __init__(self):
        self.agents = [AggressorAgent(), SkepticAgent(), SageAgent()]

    def debate(self, opportunity: Dict, global_context: Dict) -> Dict:
        """
        Run the debate for a single opportunity.
        """
        results = []
        total_vote = 0
        
        for agent in self.agents:
            res = agent.analyze(opportunity, global_context)
            results.append({
                "agent": agent.name,
                "role": agent.role,
                "icon": agent.icon,
                "vote": res['vote'], # -1 to 1
                "comment": res['comment']
            })
            total_vote += res['vote']
            
        # Determine Consensus
        avg_vote = total_vote / len(self.agents)
        verdict = "NEUTRAL"
        final_action = "WAIT"
        
        if avg_vote > 0.5:
            verdict = "STRONG BUY 🚀"
            final_action = "EXECUTE_MAX_BID"
        elif avg_vote > 0.2:
            verdict = "BUY 🟢"
            final_action = "EXECUTE_NORMAL"
        elif avg_vote < -0.5:
            verdict = "STRONG SELL 🩸"
            final_action = "DUMP_ALL"
        elif avg_vote < -0.2:
            verdict = "SELL 🔴"
            final_action = "REDUCE_POS"
            
        return {
            "verdict": verdict,
            "action": final_action,
            "consensus_score": round(avg_vote * 100, 1), # -100 to 100
            "debate_log": results
        }
