"""
📊 Report Generator - 統一報告生成模組 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- 生成中文敘述性分析 (4H/24H/7D)
- 週比較分析 (Week-over-Week)
- CEX vs DEX 分離分析
- 統一數據格式輸出

輸出：結構化報告 (可直接 JSON 輸出)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 報告目錄
REPORTS_DIR = Path(__file__).parent / "reports"
WEEKLY_HISTORY_FILE = REPORTS_DIR / "weekly_history.json"


class ReportGenerator:
    """
    統一報告生成器
    
    核心功能：
    - 將 CEX 和 DEX 數據整合為統一格式
    - 生成時間週期敘述 (4H/24H/7D)
    - 生成週比較報告
    """
    
    # 閾值配置 (統一單位: USD)
    THRESHOLDS = {
        'significant_flow': 50_000_000,      # $50M = 顯著流動
        'large_flow': 200_000_000,           # $200M = 大量流動
        'massive_flow': 500_000_000,         # $500M = 巨量流動
    }
    
    def __init__(self):
        self.weekly_history = self._load_weekly_history()
    
    def _load_weekly_history(self) -> Dict:
        """載入歷史週快照"""
        if WEEKLY_HISTORY_FILE.exists():
            try:
                with open(WEEKLY_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"無法載入週歷史: {e}")
        return {"snapshots": []}
    
    def _save_weekly_history(self):
        """儲存週快照"""
        REPORTS_DIR.mkdir(exist_ok=True)
        with open(WEEKLY_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.weekly_history, f, indent=2, ensure_ascii=False)
    
    def generate_unified_report(
        self, 
        chain_data: Dict, 
        cex_data: Dict,
        sentiment_details: Dict,
        stablecoin_marketcap: float
    ) -> Dict[str, Any]:
        """
        生成統一格式報告
        """
        # 計算 CEX 與 DEX 分開的摘要
        cex_summary = self._calculate_cex_summary(cex_data)
        dex_summary = self._calculate_dex_summary(chain_data)
        
        # 生成各時間週期敘述
        narratives = {
            '4h': self._generate_4h_narrative(cex_summary, dex_summary),
            '24h': self._generate_24h_narrative(cex_summary, dex_summary),
            '7d': self._generate_7d_narrative(cex_summary, dex_summary)
        }
        
        # 生成週比較
        weekly_comparison = self._generate_weekly_comparison(cex_summary, dex_summary)
        
        # 組裝統一報告
        report = {
            "meta": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "data_quality": self._calculate_data_quality(chain_data, cex_data),
                "version": "2.0"
            },
            
            "market_overview": {
                "sentiment": sentiment_details,
                "stablecoin_marketcap": stablecoin_marketcap,
                "total_tvl": {
                    "cex": cex_summary['total_tvl'],
                    "dex": dex_summary['total_tvl'],
                    "total": cex_summary['total_tvl'] + dex_summary['total_tvl']
                },
                "total_flow_24h": {
                    "cex": cex_summary['net_flow_24h'],
                    "dex": dex_summary['net_flow_24h'],
                    "total": cex_summary['net_flow_24h'] + dex_summary['net_flow_24h']
                }
            },
            
            "timeframes": {
                "4h": {
                    "cex": {
                        "net_flow": cex_summary['net_flow_4h'],
                        "stablecoin_flow": cex_summary['stablecoin_flow_4h'],
                        "btc_eth_flow": cex_summary['btc_eth_flow_4h']
                    },
                    "dex": {
                        "net_flow": dex_summary['net_flow_4h'],
                        "stablecoin_flow": dex_summary['stablecoin_flow_4h'],
                        "native_flow": dex_summary['native_flow_4h']
                    },
                    "narrative": narratives['4h']
                },
                "24h": {
                    "cex": {
                        "net_flow": cex_summary['net_flow_24h'],
                        "stablecoin_flow": cex_summary['stablecoin_flow_24h'],
                        "btc_eth_flow": cex_summary['btc_eth_flow_24h']
                    },
                    "dex": {
                        "net_flow": dex_summary['net_flow_24h'],
                        "stablecoin_flow": dex_summary['stablecoin_flow_24h'],
                        "native_flow": dex_summary['native_flow_24h']
                    },
                    "narrative": narratives['24h']
                },
                "7d": {
                    "cex": {
                        "net_flow": cex_summary.get('net_flow_7d', 0),
                        "change_pct": cex_summary.get('change_7d_pct', 0)
                    },
                    "dex": {
                        "net_flow": dex_summary['net_flow_7d'],
                        "stablecoin_flow": dex_summary['stablecoin_flow_7d'],
                        "change_pct": dex_summary['change_7d_pct']
                    },
                    "narrative": narratives['7d'],
                    "wow_comparison": weekly_comparison
                }
            },
            
            "cex_analysis": {
                "summary": {
                    "total_tvl": cex_summary['total_tvl'],
                    "net_flow_24h": cex_summary['net_flow_24h'],
                    "stablecoin_flow_24h": cex_summary['stablecoin_flow_24h'],
                    "btc_eth_flow_24h": cex_summary['btc_eth_flow_24h'],
                    "dominant_action": self._determine_cex_action(cex_summary),
                    "action_narrative": self._generate_cex_action_narrative(cex_summary)
                },
                "exchanges": cex_data.get('exchanges', [])
            },
            
            "dex_analysis": {
                "summary": {
                    "total_tvl": dex_summary['total_tvl'],
                    "net_flow_24h": dex_summary['net_flow_24h'],
                    "stablecoin_flow_24h": dex_summary['stablecoin_flow_24h'],
                    "native_flow_24h": dex_summary['native_flow_24h'],
                    "dominant_action": self._determine_dex_action(dex_summary),
                    "action_narrative": self._generate_dex_action_narrative(dex_summary)
                },
                "chains": chain_data.get('chains', [])
            },
            
            # 保留原始數據供向後兼容
            "chain_flows": chain_data,
            "cex_flows": cex_data
        }
        
        # 儲存週快照 (每週一次)
        self._maybe_save_weekly_snapshot(cex_summary, dex_summary)
        
        return report
    
    def _calculate_cex_summary(self, cex_data: Dict) -> Dict:
        """計算 CEX 摘要數據"""
        exchanges = cex_data.get('exchanges', [])
        valid_exchanges = [e for e in exchanges if not e.get('error')]
        
        return {
            'total_tvl': sum(e.get('total_tvl', 0) for e in valid_exchanges),
            'net_flow_24h': sum(e.get('net_flow_24h', 0) for e in valid_exchanges),
            'net_flow_4h': sum(e.get('net_flow_4h', 0) for e in valid_exchanges),
            'stablecoin_flow_24h': sum(e.get('stablecoin_flow_24h', 0) for e in valid_exchanges),
            'stablecoin_flow_4h': sum(e.get('stablecoin_flow_4h', 0) for e in valid_exchanges),
            'btc_eth_flow_24h': sum(e.get('btc_eth_flow_24h', 0) for e in valid_exchanges),
            'btc_eth_flow_4h': sum(e.get('btc_eth_flow_4h', 0) for e in valid_exchanges),
            'exchange_count': len(valid_exchanges)
        }
    
    def _calculate_dex_summary(self, chain_data: Dict) -> Dict:
        """計算 DEX/鏈上摘要數據"""
        chains = chain_data.get('chains', [])
        valid_chains = [c for c in chains if not c.get('error')]
        
        return {
            'total_tvl': sum(c.get('tvl_total', 0) for c in valid_chains),
            'net_flow_24h': sum(c.get('stable_inflow_24h', 0) + c.get('native_inflow_24h', 0) for c in valid_chains),
            'net_flow_4h': sum(c.get('stable_inflow_4h', 0) + c.get('native_inflow_4h', 0) for c in valid_chains),
            'net_flow_7d': sum(c.get('stable_inflow_7d', 0) + c.get('native_inflow_7d', 0) for c in valid_chains),
            'stablecoin_flow_24h': sum(c.get('stable_inflow_24h', 0) for c in valid_chains),
            'stablecoin_flow_4h': sum(c.get('stable_inflow_4h', 0) for c in valid_chains),
            'stablecoin_flow_7d': sum(c.get('stable_inflow_7d', 0) for c in valid_chains),
            'native_flow_24h': sum(c.get('native_inflow_24h', 0) for c in valid_chains),
            'native_flow_4h': sum(c.get('native_inflow_4h', 0) for c in valid_chains),
            'native_flow_7d': sum(c.get('native_inflow_7d', 0) for c in valid_chains),
            'change_7d_pct': sum(c.get('change_7d_pct', 0) for c in valid_chains) / max(len(valid_chains), 1),
            'chain_count': len(valid_chains)
        }
    
    def _generate_4h_narrative(self, cex: Dict, dex: Dict) -> str:
        """生成 4H 敘述性分析"""
        parts = []
        cex_stable = cex['stablecoin_flow_4h']
        cex_btc_eth = cex['btc_eth_flow_4h']
        
        if abs(cex_stable) > self.THRESHOLDS['significant_flow'] / 6:
            if cex_stable > 0:
                parts.append(f"【CEX】穩定幣流入 ${cex_stable/1e6:.0f}M，交易所買盤備戰中")
            else:
                parts.append(f"【CEX】穩定幣流出 ${abs(cex_stable)/1e6:.0f}M，買盤資金撤離")
        
        if abs(cex_btc_eth) > self.THRESHOLDS['significant_flow'] / 6:
            if cex_btc_eth > 0:
                parts.append(f"BTC/ETH 流入交易所 ${cex_btc_eth/1e6:.0f}M (潛在賣壓)")
            else:
                parts.append(f"BTC/ETH 流出交易所 ${abs(cex_btc_eth)/1e6:.0f}M (囤貨信號)")
        
        dex_stable = dex['stablecoin_flow_4h']
        if abs(dex_stable) > self.THRESHOLDS['significant_flow'] / 6:
            if dex_stable > 0:
                parts.append(f"【DEX】穩定幣流入鏈上 ${dex_stable/1e6:.0f}M，DeFi 活動增加")
            else:
                parts.append(f"【DEX】穩定幣流出鏈上 ${abs(dex_stable)/1e6:.0f}M，資金撤離 DeFi")
        
        if not parts:
            parts.append("過去 4 小時資金流向平穩，無顯著異動")
        
        return " | ".join(parts)
    
    def _generate_24h_narrative(self, cex: Dict, dex: Dict) -> str:
        """生成 24H 敘述性分析"""
        parts = []
        cex_stable = cex['stablecoin_flow_24h']
        cex_btc_eth = cex['btc_eth_flow_24h']
        
        if cex_stable > self.THRESHOLDS['large_flow']:
            parts.append(f"🟢 CEX 穩定幣大量流入 ${cex_stable/1e6:.0f}M，市場積極備戰買入")
        elif cex_stable > self.THRESHOLDS['significant_flow']:
            parts.append(f"🟡 CEX 穩定幣流入 ${cex_stable/1e6:.0f}M，買盤逐步累積")
        elif cex_stable < -self.THRESHOLDS['large_flow']:
            parts.append(f"🔴 CEX 穩定幣大量流出 ${abs(cex_stable)/1e6:.0f}M，買盤資金撤離")
        
        if cex_btc_eth > self.THRESHOLDS['large_flow']:
            parts.append(f"⚠️ BTC/ETH 大量流入交易所 ${cex_btc_eth/1e6:.0f}M，賣壓警告")
        elif cex_btc_eth < -self.THRESHOLDS['large_flow']:
            parts.append(f"💎 BTC/ETH 大量流出交易所 ${abs(cex_btc_eth)/1e6:.0f}M，長期囤貨信號")
        
        dex_net = dex['net_flow_24h']
        if dex_net > self.THRESHOLDS['large_flow']:
            parts.append(f"🌊 鏈上 TVL 增加 ${dex_net/1e6:.0f}M，DeFi 活動活躍")
        elif dex_net < -self.THRESHOLDS['large_flow']:
            parts.append(f"📉 鏈上 TVL 減少 ${abs(dex_net)/1e6:.0f}M，資金撤離 DeFi")
        
        if cex_stable > 0 and cex_btc_eth < 0:
            parts.append("📊 綜合：買盤積極備戰 (穩定幣入+BTC/ETH出)")
        elif cex_stable < 0 and cex_btc_eth > 0:
            parts.append("📊 綜合：賣壓風險升高 (穩定幣出+BTC/ETH入)")
        
        if not parts:
            parts.append("過去 24 小時市場資金流向平穩，無明顯異動")
        
        return " | ".join(parts)
    
    def _generate_7d_narrative(self, cex: Dict, dex: Dict) -> str:
        """生成 7D 敘述性分析"""
        parts = []
        dex_7d = dex.get('net_flow_7d', 0)
        dex_change = dex.get('change_7d_pct', 0)
        
        if dex_7d > self.THRESHOLDS['massive_flow']:
            parts.append(f"🚀 本週鏈上 TVL 大幅增長 ${dex_7d/1e9:.2f}B (+{dex_change:.1f}%)")
        elif dex_7d > self.THRESHOLDS['large_flow']:
            parts.append(f"📈 本週鏈上 TVL 穩健增長 ${dex_7d/1e6:.0f}M (+{dex_change:.1f}%)")
        elif dex_7d < -self.THRESHOLDS['massive_flow']:
            parts.append(f"📉 本週鏈上 TVL 大幅下降 ${abs(dex_7d)/1e9:.2f}B ({dex_change:.1f}%)")
        elif dex_7d < -self.THRESHOLDS['large_flow']:
            parts.append(f"⚠️ 本週鏈上 TVL 下降 ${abs(dex_7d)/1e6:.0f}M ({dex_change:.1f}%)")
        else:
            parts.append(f"本週鏈上 TVL 變化 {dex_change:+.1f}%，整體平穩")
        
        return " | ".join(parts)
    
    def _generate_weekly_comparison(self, cex: Dict, dex: Dict) -> Dict:
        """生成週比較分析"""
        last_week = self._get_last_week_snapshot()
        
        if not last_week:
            return {
                "available": False,
                "narrative": "首次運行，尚無上週數據可供比較"
            }
        
        cex_flow_change = cex['net_flow_24h'] - last_week.get('cex_net_flow_24h', 0)
        dex_flow_change = dex['net_flow_24h'] - last_week.get('dex_net_flow_24h', 0)
        
        cex_change_pct = (cex_flow_change / abs(last_week.get('cex_net_flow_24h', 1))) * 100 if last_week.get('cex_net_flow_24h') else 0
        dex_change_pct = (dex_flow_change / abs(last_week.get('dex_net_flow_24h', 1))) * 100 if last_week.get('dex_net_flow_24h') else 0
        
        parts = []
        if cex_change_pct > 20:
            parts.append(f"CEX 資金流入較上週增加 {cex_change_pct:.0f}%")
        elif cex_change_pct < -20:
            parts.append(f"CEX 資金流入較上週減少 {abs(cex_change_pct):.0f}%")
        
        if dex_change_pct > 20:
            parts.append(f"DEX 資金流入較上週增加 {dex_change_pct:.0f}%")
        elif dex_change_pct < -20:
            parts.append(f"DEX 資金流入較上週減少 {abs(dex_change_pct):.0f}%")
        
        return {
            "available": True,
            "cex_flow_change_pct": round(cex_change_pct, 1),
            "dex_flow_change_pct": round(dex_change_pct, 1),
            "last_week_date": last_week.get('date', 'N/A'),
            "narrative": " | ".join(parts) if parts else "與上週相比資金流向變化不大"
        }
    
    def _get_last_week_snapshot(self) -> Optional[Dict]:
        """獲取上週快照"""
        snapshots = self.weekly_history.get('snapshots', [])
        if snapshots:
            return snapshots[-1]
        return None
    
    def _maybe_save_weekly_snapshot(self, cex: Dict, dex: Dict):
        """如果是新的一週，儲存快照"""
        today = datetime.now()
        week_key = today.strftime('%Y-W%W')
        
        snapshots = self.weekly_history.get('snapshots', [])
        existing_weeks = [s.get('week_key') for s in snapshots]
        
        if week_key not in existing_weeks:
            snapshot = {
                'week_key': week_key,
                'date': today.strftime('%Y-%m-%d'),
                'cex_net_flow_24h': cex['net_flow_24h'],
                'cex_stablecoin_flow_24h': cex['stablecoin_flow_24h'],
                'dex_net_flow_24h': dex['net_flow_24h'],
                'dex_stablecoin_flow_24h': dex['stablecoin_flow_24h']
            }
            snapshots.append(snapshot)
            self.weekly_history['snapshots'] = snapshots[-12:]
            self._save_weekly_history()
            logger.info(f"💾 已儲存週快照: {week_key}")
    
    def _determine_cex_action(self, cex: Dict) -> str:
        """判斷 CEX 主要行動"""
        stable = cex['stablecoin_flow_24h']
        btc_eth = cex['btc_eth_flow_24h']
        
        if stable > self.THRESHOLDS['significant_flow'] and btc_eth < 0:
            return "積極買入準備"
        elif stable > self.THRESHOLDS['significant_flow']:
            return "買盤累積"
        elif btc_eth > self.THRESHOLDS['significant_flow']:
            return "潛在賣壓"
        elif stable < -self.THRESHOLDS['significant_flow'] and btc_eth < -self.THRESHOLDS['significant_flow']:
            return "全面提幣"
        elif stable < -self.THRESHOLDS['significant_flow']:
            return "穩定幣撤離"
        else:
            return "持平觀望"
    
    def _determine_dex_action(self, dex: Dict) -> str:
        """判斷 DEX 主要行動"""
        net_flow = dex['net_flow_24h']
        stable = dex['stablecoin_flow_24h']
        
        if stable > self.THRESHOLDS['significant_flow']:
            return "DeFi 資金流入"
        elif stable < -self.THRESHOLDS['significant_flow']:
            return "DeFi 資金撤離"
        elif net_flow > 0:
            return "TVL 增長中"
        elif net_flow < 0:
            return "TVL 下降中"
        else:
            return "持平穩定"
    
    def _generate_cex_action_narrative(self, cex: Dict) -> str:
        """生成 CEX 行動敘述"""
        action = self._determine_cex_action(cex)
        stable = cex['stablecoin_flow_24h']
        btc_eth = cex['btc_eth_flow_24h']
        
        narratives = {
            "積極買入準備": f"交易所穩定幣流入 ${stable/1e6:.0f}M 同時 BTC/ETH 流出 ${abs(btc_eth)/1e6:.0f}M，資金正積極準備買入",
            "買盤累積": f"穩定幣持續流入交易所 ${stable/1e6:.0f}M，買盤力道增強",
            "潛在賣壓": f"BTC/ETH 流入交易所 ${btc_eth/1e6:.0f}M，需警惕賣壓",
            "全面提幣": f"穩定幣與 BTC/ETH 同時流出交易所，市場進入囤貨模式",
            "穩定幣撤離": f"穩定幣流出交易所 ${abs(stable)/1e6:.0f}M，買盤資金減少",
            "持平觀望": "交易所資金流向平穩，市場觀望中"
        }
        return narratives.get(action, "無特殊行動")
    
    def _generate_dex_action_narrative(self, dex: Dict) -> str:
        """生成 DEX 行動敘述"""
        action = self._determine_dex_action(dex)
        stable = dex['stablecoin_flow_24h']
        net = dex['net_flow_24h']
        
        narratives = {
            "DeFi 資金流入": f"穩定幣流入鏈上 ${stable/1e6:.0f}M，DeFi 活動增加",
            "DeFi 資金撤離": f"穩定幣從鏈上流出 ${abs(stable)/1e6:.0f}M，資金撤離 DeFi",
            "TVL 增長中": f"鏈上總 TVL 增加 ${net/1e6:.0f}M",
            "TVL 下降中": f"鏈上總 TVL 減少 ${abs(net)/1e6:.0f}M",
            "持平穩定": "鏈上資金流向平穩"
        }
        return narratives.get(action, "無特殊行動")
    
    def _calculate_data_quality(self, chain_data: Dict, cex_data: Dict) -> int:
        """計算整體數據品質分數"""
        scores = []
        
        for chain in chain_data.get('chains', []):
            scores.append(chain.get('confidence_score', 50))
        
        for ex in cex_data.get('exchanges', []):
            scores.append(ex.get('confidence_score', 50))
        
        if scores:
            return int(sum(scores) / len(scores))
        return 50


if __name__ == '__main__':
    generator = ReportGenerator()
    print("ReportGenerator 初始化成功")
