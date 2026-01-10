
"""
💰 V8 Treasury Manager - 國庫與複利系統
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能:
1. 追蹤系統的虛擬國庫總資本
2. 使用凱利公式計算最佳倉位
3. 利潤自動分配 (複利/營運金/可提取)
4. 持久化儲存國庫狀態
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class TreasuryManager:
    """
    V8 Treasury Core - 資產管理與複利系統
    
    使用凱利公式 (Kelly Criterion) 計算最佳倉位
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.state_file = Path(__file__).parent / "reports" / "treasury_state.json"
        self.state = self._load_state(initial_capital)
        
        # Allocation ratios
        self.ALLOCATION = {
            'trading': 0.70,      # 70% 用於交易
            'reserve': 0.20,      # 20% 營運準備金
            'compound': 0.10      # 10% 強制複利
        }
        
    def _load_state(self, default_capital: float) -> Dict:
        """Load treasury state from disk"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        # Initialize new treasury
        return {
            'initial_capital': default_capital,
            'current_capital': default_capital,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'reserve_fund': 0.0,
            'withdrawable': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
    
    def _save_state(self):
        """Persist treasury state to disk"""
        self.state['updated_at'] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
            
    def calculate_kelly_fraction(self, win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
        """
        凱利公式: f* = (bp - q) / b
        where:
            b = odds received on the bet (avg_win / avg_loss)
            p = probability of winning
            q = probability of losing (1 - p)
        
        Returns: Optimal fraction of capital to bet (0 to 1)
        """
        if avg_loss_pct == 0 or win_rate <= 0 or avg_win_pct <= 0:
            return 0.05  # Default 5% if no data
            
        b = avg_win_pct / abs(avg_loss_pct)
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        
        # Half-Kelly for safety (less aggressive)
        kelly = kelly / 2
        
        # Clamp to 0.02 - 0.20 (2% to 20% of capital)
        return max(0.02, min(0.20, kelly))
    
    def get_position_size(self, confidence: int = 80) -> Dict:
        """
        根據當前資本和凱利公式，計算建議的單筆倉位大小
        
        Args:
            confidence: Signal confidence (0-100)
        """
        # Get historical stats
        total = self.state['total_trades']
        wins = self.state['winning_trades']
        
        if total < 5:
            # Not enough data, use conservative sizing
            win_rate = 0.5
            avg_win = 5.0
            avg_loss = 3.0
        else:
            win_rate = wins / total
            avg_win = 5.0  # Placeholder, will be calculated from actual trades
            avg_loss = 3.0
            
        kelly_fraction = self.calculate_kelly_fraction(win_rate, avg_win, avg_loss)
        
        # Adjust by confidence
        confidence_mult = confidence / 100
        adjusted_fraction = kelly_fraction * confidence_mult
        
        tradeable_capital = self.state['current_capital'] * self.ALLOCATION['trading']
        position_size = tradeable_capital * adjusted_fraction
        
        return {
            'kelly_fraction': round(kelly_fraction, 4),
            'adjusted_fraction': round(adjusted_fraction, 4),
            'recommended_position_usd': round(position_size, 2),
            'tradeable_capital': round(tradeable_capital, 2),
            'current_total_capital': round(self.state['current_capital'], 2)
        }
    
    def record_trade_result(self, pnl_usd: float, is_win: bool):
        """Record a closed trade result and update treasury"""
        self.state['total_trades'] += 1
        
        if is_win:
            self.state['winning_trades'] += 1
        else:
            self.state['losing_trades'] += 1
            
        self.state['realized_pnl'] += pnl_usd
        
        # Profit distribution
        if pnl_usd > 0:
            compound_amount = pnl_usd * self.ALLOCATION['compound']
            reserve_amount = pnl_usd * self.ALLOCATION['reserve']
            withdrawable_amount = pnl_usd * (1 - self.ALLOCATION['compound'] - self.ALLOCATION['reserve'])
            
            self.state['current_capital'] += compound_amount
            self.state['reserve_fund'] += reserve_amount
            self.state['withdrawable'] += withdrawable_amount
            
            logger.info(f"💰 Treasury: Profit ${pnl_usd:.2f} → Compound ${compound_amount:.2f} / Reserve ${reserve_amount:.2f} / Withdraw ${withdrawable_amount:.2f}")
        else:
            # Loss comes from trading capital
            self.state['current_capital'] += pnl_usd  # pnl_usd is negative
            
        self._save_state()
        
    def update_unrealized(self, unrealized_pnl: float):
        """Update unrealized PnL for reporting"""
        self.state['unrealized_pnl'] = unrealized_pnl
        self._save_state()
        
    def get_summary(self) -> Dict:
        """Get treasury summary for reporting"""
        total = self.state['total_trades']
        win_rate = (self.state['winning_trades'] / total * 100) if total > 0 else 0
        
        return {
            'current_capital': round(self.state['current_capital'], 2),
            'initial_capital': self.state['initial_capital'],
            'realized_pnl': round(self.state['realized_pnl'], 2),
            'unrealized_pnl': round(self.state['unrealized_pnl'], 2),
            'total_pnl': round(self.state['realized_pnl'] + self.state['unrealized_pnl'], 2),
            'roi_pct': round(((self.state['current_capital'] - self.state['initial_capital']) / self.state['initial_capital']) * 100, 2),
            'reserve_fund': round(self.state['reserve_fund'], 2),
            'withdrawable': round(self.state['withdrawable'], 2),
            'total_trades': total,
            'win_rate': round(win_rate, 1),
            'updated_at': self.state['updated_at']
        }
