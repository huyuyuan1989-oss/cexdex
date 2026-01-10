
"""
🛡️ V8 Hedge Manager - 動態對沖保護系統 (The Shield)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能:
1. 監控系統性風險指標 (F&G 驟降, 費率極端)
2. 當風險超過閾值時，自動建議開啟對沖倉位
3. 計算 Delta 中性所需的對沖數量
4. 追蹤對沖狀態
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class HedgeManager:
    """
    V8 The Shield - 動態對沖保護系統
    
    當市場風險升高時，自動計算並建議對沖倉位
    """
    
    def __init__(self, state_file: Path = None):
        self.state_file = state_file or (Path(__file__).parent / "reports" / "hedge_state.json")
        self.state = self._load_state()
        
        # Risk thresholds
        self.THRESHOLDS = {
            'fng_crash': 10,      # F&G 驟降超過此值觸發警報
            'fng_extreme_fear': 15,  # 極度恐慌
            'fng_extreme_greed': 85, # 極度貪婪
            'funding_hot': 0.05,     # 費率過熱
            'drawdown_alert': -5.0   # 回撤超過 5% 觸發
        }
        
    def _load_state(self) -> Dict:
        """Load hedge state from disk"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'hedge_active': False,
            'hedge_direction': None,  # 'SHORT' or 'LONG'
            'hedge_size_usd': 0,
            'hedge_reason': None,
            'last_fng': 50,
            'activated_at': None,
            'updated_at': datetime.now().isoformat()
        }
    
    def _save_state(self):
        """Persist hedge state to disk"""
        self.state['updated_at'] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def analyze_risk(self, 
                     fng_value: int, 
                     funding_btc: float, 
                     unrealized_pnl_pct: float,
                     portfolio_value: float) -> Dict[str, Any]:
        """
        分析當前風險水平，決定是否需要對沖
        
        Returns:
            {
                'risk_level': 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL',
                'hedge_action': 'NONE' | 'ACTIVATE_HEDGE' | 'DEACTIVATE_HEDGE',
                'recommended_hedge': {...} or None,
                'signals': [...]
            }
        """
        signals = []
        risk_score = 0
        
        # === Signal 1: F&G Crash Detection ===
        prev_fng = self.state.get('last_fng', 50)
        fng_change = fng_value - prev_fng
        
        if fng_change < -self.THRESHOLDS['fng_crash']:
            signals.append(f"🚨 F&G 驟降警報! ({prev_fng} → {fng_value}, Δ{fng_change})")
            risk_score += 40
            
        # === Signal 2: Extreme Fear (Contrarian - Less Risk) ===
        if fng_value <= self.THRESHOLDS['fng_extreme_fear']:
            signals.append(f"😱 極度恐慌 (F&G={fng_value}): 市場底部區域，對沖不必要")
            risk_score -= 20  # Reduce risk score in extreme fear (good for buying)
            
        # === Signal 3: Extreme Greed (High Risk) ===
        if fng_value >= self.THRESHOLDS['fng_extreme_greed']:
            signals.append(f"🔥 極度貪婪 (F&G={fng_value}): 崩盤風險極高!")
            risk_score += 50
            
        # === Signal 4: Funding Rate Extreme ===
        if funding_btc > self.THRESHOLDS['funding_hot']:
            signals.append(f"📈 費率過熱 ({funding_btc*100:.3f}%): 多頭擁擠，閃崩風險")
            risk_score += 30
            
        # === Signal 5: Portfolio Drawdown ===
        if unrealized_pnl_pct < self.THRESHOLDS['drawdown_alert']:
            signals.append(f"📉 組合回撤警報 ({unrealized_pnl_pct:.2f}%): 啟動防禦模式")
            risk_score += 35
            
        # === Determine Risk Level ===
        if risk_score >= 80:
            risk_level = 'CRITICAL'
        elif risk_score >= 50:
            risk_level = 'HIGH'
        elif risk_score >= 20:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
            
        # === Determine Hedge Action ===
        hedge_action = 'NONE'
        recommended_hedge = None
        
        if risk_level in ['CRITICAL', 'HIGH'] and not self.state['hedge_active']:
            hedge_action = 'ACTIVATE_HEDGE'
            # Calculate hedge size (100% of portfolio for delta neutral)
            hedge_size = portfolio_value * 1.0
            recommended_hedge = {
                'direction': 'SHORT',  # Hedge long exposure
                'size_usd': round(hedge_size, 2),
                'reason': f"Risk Level: {risk_level} (Score: {risk_score})",
                'target_delta': 0  # Delta Neutral
            }
            
        elif risk_level == 'LOW' and self.state['hedge_active']:
            hedge_action = 'DEACTIVATE_HEDGE'
            
        # Update state
        self.state['last_fng'] = fng_value
        self._save_state()
        
        # Log
        logger.info(f"🛡️ V8 Shield: Risk Level = {risk_level} (Score: {risk_score})")
        for sig in signals:
            logger.info(f"   → {sig}")
            
        if hedge_action == 'ACTIVATE_HEDGE':
            logger.warning(f"⚠️ HEDGE RECOMMENDED: {recommended_hedge}")
            
        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'hedge_action': hedge_action,
            'recommended_hedge': recommended_hedge,
            'signals': signals,
            'hedge_currently_active': self.state['hedge_active']
        }
    
    def activate_hedge(self, direction: str, size_usd: float, reason: str):
        """Activate hedge position (for paper trading simulation)"""
        self.state['hedge_active'] = True
        self.state['hedge_direction'] = direction
        self.state['hedge_size_usd'] = size_usd
        self.state['hedge_reason'] = reason
        self.state['activated_at'] = datetime.now().isoformat()
        self._save_state()
        logger.info(f"🛡️ HEDGE ACTIVATED: {direction} ${size_usd} - {reason}")
        
    def deactivate_hedge(self):
        """Deactivate hedge position"""
        self.state['hedge_active'] = False
        self.state['hedge_direction'] = None
        self.state['hedge_size_usd'] = 0
        self.state['hedge_reason'] = None
        self.state['activated_at'] = None
        self._save_state()
        logger.info("🛡️ HEDGE DEACTIVATED: Risk returned to normal levels")
        
    def get_status(self) -> Dict:
        """Get current hedge status for reporting"""
        return {
            'active': self.state['hedge_active'],
            'direction': self.state.get('hedge_direction'),
            'size_usd': self.state.get('hedge_size_usd', 0),
            'reason': self.state.get('hedge_reason'),
            'activated_at': self.state.get('activated_at'),
            'last_fng': self.state.get('last_fng', 50)
        }
