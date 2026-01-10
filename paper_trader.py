
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from data_provider import DataProvider

logger = logging.getLogger(__name__)

class PaperTrader:
    """
    V6 Pre-cursor: Paper Trading Engine (模擬交易核心)
    
    功能:
    1. 接收 Alpha Hunter 下單訊號
    2. 自動記錄模擬進場 (使用即時價格)
    3. 每日計算持倉盈虧 (PnL)
    4. 產生交易績效報告
    """
    
    def __init__(self, provider: DataProvider):
        self.provider = provider
        self.trades_file = Path(__file__).parent / "reports" / "paper_trades.json"
        self.history_file = Path(__file__).parent / "reports" / "trade_history.csv"
        self.positions = self._load_positions()
        
        # Mapping Chain to Tradeable Token (V7 Expanded)
        self.CHAIN_TO_TOKEN = {
            # === Tier 1: Major L1s ===
            'ETHEREUM': 'ETH',
            'SOLANA': 'SOL',
            'BSC': 'BNB',
            'TRON': 'TRX',
            'AVALANCHE': 'AVAX',
            # === Tier 2: L2 Ecosystems ===
            'ARBITRUM': 'ARB',
            'OPTIMISM': 'OP',
            'BASE': 'ETH',       # Base trades correlated with ETH
            'POLYGON': 'MATIC',
            'ZKSYNC ERA': 'ZK',
            'LINEA': 'ETH',      # Linea is ETH L2
            'SCROLL': 'ETH',     # Scroll is ETH L2
            'BLAST': 'BLAST',
            'MANTA': 'MANTA',
            'MANTLE': 'MNT',
            # === Tier 3: Emerging L1s ===
            'SUI': 'SUI',
            'APTOS': 'APT',
            'SEI': 'SEI',
            'NEAR': 'NEAR',
            'FANTOM': 'FTM',
            'COSMOS': 'ATOM',
            'CARDANO': 'ADA',
            'CRONOS': 'CRO',
            # === Tier 4: Others ===
            'TON': 'TON',
            'STARKNET': 'STRK',
            # === Bonus: Market Sentiment Proxies ===
            'DOGE': 'DOGE',
            'PEPE': 'PEPE',
            'SHIB': 'SHIB'
        }

    def _load_positions(self) -> List[Dict]:
        if self.trades_file.exists():
            try:
                with open(self.trades_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_positions(self):
        with open(self.trades_file, 'w', encoding='utf-8') as f:
            json.dump(self.positions, f, indent=2, ensure_ascii=False)

    async def update_positions(self):
        """更新現有持倉的 PnL"""
        if not self.positions:
            return

        active_symbols = set(p['symbol'] for p in self.positions if p['status'] == 'OPEN')
        if not active_symbols:
            return

        # Fetch current prices
        prices = await self.provider.get_token_prices(list(active_symbols))
        
        total_unrealized_pnl_pct = 0
        total_pnl_usd = 0
        
        # Simulated position size: $1000 per trade for USD PnL display
        TRADE_SIZE = 1000
        
        for p in self.positions:
            if p['status'] == 'OPEN':
                current_price = prices.get(p['symbol'])
                if current_price:
                    p['current_price'] = current_price
                    # PnL % = (Current - Entry) / Entry * 100
                    pnl_pct = ((current_price - p['entry_price']) / p['entry_price']) * 100
                    if p['direction'] == 'SHORT':
                        pnl_pct *= -1
                    
                    p['pnl_pct'] = round(pnl_pct, 2)
                    p['pnl_usd'] = round(TRADE_SIZE * (pnl_pct / 100), 2)
                    
                    total_unrealized_pnl_pct += pnl_pct
                    total_pnl_usd += p['pnl_usd']
                    
                    # Auto-Close logic (Take Profit / Stop Loss Simulation)
                    if pnl_pct > 15: # TP
                        p['status'] = 'CLOSED (TP)'
                        p['exit_price'] = current_price
                        p['exit_time'] = datetime.now().isoformat()
                    elif pnl_pct < -10: # SL
                        p['status'] = 'CLOSED (SL)'
                        p['exit_price'] = current_price
                        p['exit_time'] = datetime.now().isoformat()
        
        self._save_positions()
        logger.info(f"💰 Paper Trader: Updated {len(active_symbols)} positions. Total Unrealized PnL: {total_unrealized_pnl_pct:.2f}% (${total_pnl_usd:+.2f})")


    async def execute_signals(self, opportunities: List[Dict]):
        """
        執行 Alpha Hunter 的訊號
        """
        # Filter high confidence signals
        tradeable_opps = [
            op for op in opportunities 
            if op['score'] >= 80 and op['type'] == 'CHAIN'
        ]
        
        if not tradeable_opps:
            return

        # Gather symbols to fetch price
        symbols_to_fetch = set()
        for op in tradeable_opps:
            chain = op['asset']
            token = self.CHAIN_TO_TOKEN.get(chain)
            if token:
                symbols_to_fetch.add(token)
        
        prices = await self.provider.get_token_prices(list(symbols_to_fetch))
        
        for op in tradeable_opps:
            chain = op['asset']
            token = self.CHAIN_TO_TOKEN.get(chain)
            if not token or token not in prices:
                continue
                
            price = prices[token]
            direction = 'LONG' if '買入' in op['direction'] else 'SHORT'
            
            # Check if we already have an open position for this asset
            existing = next((p for p in self.positions if p['symbol'] == token and p['status'] == 'OPEN'), None)
            
            if not existing:
                # Open New Position
                new_trade = {
                    "id": f"{token}-{int(datetime.now().timestamp())}",
                    "symbol": token,
                    "direction": direction,
                    "entry_price": price,
                    "entry_time": datetime.now().isoformat(),
                    "reason": op['reason'],
                    "confidence": op['score'],
                    "status": "OPEN",
                    "pnl_pct": 0.0,
                    "pnl_usd": 0.0
                }
                self.positions.append(new_trade)
                logger.info(f"🆕 Paper Trade Opened: {direction} {token} @ ${price} ({op['reason']})")
                
        self._save_positions()
