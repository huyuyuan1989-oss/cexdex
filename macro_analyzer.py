
"""
🧠 V8 Macro Intelligence - 宏觀意圖解析器
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能:
1. 分析恐慌貪婪指數變化趨勢 (而非單一數值)
2. 分析穩定幣流動趨勢 (7日趨勢)
3. 偵測市場「轉折點」並產生宏觀偏見 (Macro Bias)
4. 將 Bias 注入 HiveMind，影響代理人權重
"""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MacroAnalyzer:
    """
    V8 Macro Intelligence Core
    
    產出: macro_bias (float, -1.0 to +1.0)
    - 正值 = 宏觀看多 (Aggressor 權重增加)
    - 負值 = 宏觀看空 (Skeptic 權重增加)
    - 0 = 中性 (正常辯論)
    """
    
    def __init__(self):
        self.history = []  # Store recent readings for trend analysis
        
    def analyze(self, fng_data: Dict, derivs_data: Dict, stablecoin_flow: float) -> Dict[str, Any]:
        """
        執行宏觀分析，產出 Macro Bias
        
        Args:
            fng_data: Fear & Greed Index data
            derivs_data: Derivatives data (Funding, OI)
            stablecoin_flow: 24h stablecoin net flow (USD)
        
        Returns:
            {
                'macro_bias': float (-1.0 to 1.0),
                'regime': str (RISK_ON, RISK_OFF, NEUTRAL),
                'signals': list of triggered signals,
                'description': str
            }
        """
        signals = []
        bias = 0.0
        
        # === Signal 1: Fear & Greed Extreme Zones ===
        fng_value = fng_data.get('value', 50)
        
        if fng_value <= 15:
            # 極度恐慌 = 逆向做多信號
            signals.append(f"🩸 極度恐慌 (F&G={fng_value}): 市場血流成河，貪婪時刻!")
            bias += 0.4  # Bullish bias
        elif fng_value <= 25:
            signals.append(f"😨 恐慌區 (F&G={fng_value}): 市場情緒低迷，留意反彈機會")
            bias += 0.2
        elif fng_value >= 85:
            # 極度貪婪 = 逆向做空信號
            signals.append(f"🔥 極度貪婪 (F&G={fng_value}): 市場狂熱，小心崩盤!")
            bias -= 0.4  # Bearish bias
        elif fng_value >= 75:
            signals.append(f"🟢 貪婪區 (F&G={fng_value}): 風險偏高，收緊止盈")
            bias -= 0.2
            
        # === Signal 2: Funding Rate Extremes ===
        btc_funding = derivs_data.get('funding_rates', {}).get('BTC', 0)
        
        if btc_funding > 0.05:  # > 0.05% = 過熱
            signals.append(f"📈 費率過熱 (Funding={btc_funding*100:.3f}%): 多頭擁擠，軋空風險低")
            bias -= 0.3
        elif btc_funding < -0.02:  # < -0.02% = 負費率
            signals.append(f"📉 負費率 (Funding={btc_funding*100:.3f}%): 空頭付費，軋空預期!")
            bias += 0.3
            
        # === Signal 3: Stablecoin Flow Trend ===
        if stablecoin_flow > 100_000_000:  # +$100M+
            signals.append(f"💵 穩定幣大量流入 (+${stablecoin_flow/1e6:.1f}M): 熱錢湧入!")
            bias += 0.2
        elif stablecoin_flow < -100_000_000:  # -$100M+
            signals.append(f"💸 穩定幣大量流出 (${stablecoin_flow/1e6:.1f}M): 資金撤離!")
            bias -= 0.2
            
        # === Determine Regime ===
        if bias >= 0.3:
            regime = "RISK_ON"
            description = "宏觀環境偏多，Aggressor 權重增強"
        elif bias <= -0.3:
            regime = "RISK_OFF"
            description = "宏觀環境偏空，Skeptic 權重增強"
        else:
            regime = "NEUTRAL"
            description = "宏觀環境中性，維持正常辯論權重"
            
        # Clamp bias to [-1, 1]
        bias = max(-1.0, min(1.0, bias))
        
        logger.info(f"🧠 V8 Macro: Regime={regime}, Bias={bias:+.2f}")
        for sig in signals:
            logger.info(f"   → {sig}")
        
        return {
            'macro_bias': round(bias, 2),
            'regime': regime,
            'signals': signals,
            'description': description,
            'timestamp': datetime.now().isoformat()
        }


class TreasuryManager:
    """
    V8 Treasury Core - 資產管理與複利系統
    
    使用凱利公式 (Kelly Criterion) 計算最佳倉位
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.capital = initial_capital
        self.allocation = {
            'trading': 0.70,      # 70% 用於交易
            'reserve': 0.20,      # 20% 營運準備金
            'compound': 0.10      # 10% 強制複利
        }
        
    def calculate_kelly_position(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        凱利公式: f* = (bp - q) / b
        where:
            b = odds received on the bet (avg_win / avg_loss)
            p = probability of winning
            q = probability of losing (1 - p)
        
        Returns: Optimal fraction of capital to bet (0 to 1)
        """
        if avg_loss == 0 or win_rate <= 0:
            return 0.0
            
        b = avg_win / abs(avg_loss)
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        
        # Half-Kelly for safety (less aggressive)
        kelly = kelly / 2
        
        # Clamp to 0.01 - 0.25 (1% to 25% of capital)
        return max(0.01, min(0.25, kelly))
    
    def get_position_size(self, win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> Dict:
        """
        根據當前資本和凱利公式，計算建議的單筆倉位大小
        """
        kelly_fraction = self.calculate_kelly_position(
            win_rate, 
            avg_win_pct, 
            avg_loss_pct
        )
        
        tradeable_capital = self.capital * self.allocation['trading']
        position_size = tradeable_capital * kelly_fraction
        
        return {
            'kelly_fraction': round(kelly_fraction, 4),
            'recommended_position_usd': round(position_size, 2),
            'max_risk_usd': round(position_size * (avg_loss_pct/100), 2),
            'capital_utilization': f"{kelly_fraction*100:.1f}%"
        }
