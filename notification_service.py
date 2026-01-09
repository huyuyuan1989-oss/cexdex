"""
🔔 Notification Service - Discord 通知模組 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- Discord Webhook 通知 (Embed 格式)
- 支援多個 Webhook 同時發送
- 自動判斷 Bullish/Bearish 並使用對應顏色
- 基於資金流向觸發警報

依賴：requests (標準 HTTP 請求)
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ================= Discord Webhook 設定 =================

# 預設 Webhook URLs (可透過環境變數覆蓋)
DEFAULT_WEBHOOKS = [
    "https://discord.com/api/webhooks/1457246054394363990/6vOf6A1Tg6ndqE-NNvfwEPgJM6NQgZCcmwUY5zYn1enVdBI1kMj140KT3Iq4DUD7_u4N",
    "https://discord.com/api/webhooks/1458033972650180640/uEoOBJBrcHtKeVY8OsyY8Qhnzicxjioz_1h9LDKQ0D0y4qX4QVp-OclnaBcPUez9lHrb"
]

# 顏色定義
COLORS = {
    'green': 0x00ff00,   # Bullish
    'red': 0xff0000,     # Bearish
    'yellow': 0xffff00,  # Neutral
    'blue': 0x3498db,    # Info
}

# 儀表板 URL
DASHBOARD_URL = "https://huyuyuan1989-oss.github.io/cexdex/reports/index.html"

# 閾值設定
THRESHOLDS = {
    'stablecoin_inflow': 100_000_000,  # $100M
    'btc_eth_inflow': 100_000_000,     # $100M
}


def generate_insight(signal_type: str, amount: float) -> str:
    """
    生成深度分析洞察文字
    
    Args:
        signal_type: 信號類型 ('Bullish_Stablecoin' 或 'Bearish_Dump')
        amount: 金額 (USD)
    
    Returns:
        分析洞察文字
    """
    if signal_type == 'Bullish_Stablecoin':
        return "檢測到異常規模的購買力儲備。主力可能正在積累籌碼準備上攻。"
    elif signal_type == 'Bearish_Dump':
        return "檢測到大額風險資產充值。可能存在潛在的拋售壓力，建議避險。"
    else:
        return "市場資金流向正常，無明顯異動。"


def get_webhook_urls() -> List[str]:
    """
    獲取 Discord Webhook URLs
    
    優先使用環境變數，否則使用預設值
    """
    env_webhooks = os.getenv('DISCORD_WEBHOOK_URLS')
    if env_webhooks:
        return [url.strip() for url in env_webhooks.split(',') if url.strip()]
    
    single_webhook = os.getenv('DISCORD_WEBHOOK_URL')
    if single_webhook:
        return [single_webhook] + DEFAULT_WEBHOOKS[1:]  # 第一個用環境變數，第二個用預設
    
    return DEFAULT_WEBHOOKS


def send_discord_alert(
    title: str,
    message: str,
    color: int,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer: Optional[str] = None
) -> bool:
    """
    發送 Discord Embed 警報到所有 Webhooks
    
    Args:
        title: Embed 標題
        message: Embed 描述
        color: Embed 顏色 (十六進制整數)
        fields: Embed 欄位列表 [{name, value, inline}, ...]
        footer: 頁腳文字
    
    Returns:
        True 如果至少一個 Webhook 發送成功
    """
    webhooks = get_webhook_urls()
    
    if not webhooks:
        logger.warning("⚠️ 未設定 Discord Webhook URL")
        return False
    
    # 構建 Embed
    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if fields:
        embed["fields"] = fields
    
    if footer:
        embed["footer"] = {"text": footer}
    else:
        embed["footer"] = {"text": "資金流向監控系統 | Capital Flow Monitor"}
    
    payload = {
        "embeds": [embed]
    }
    
    success_count = 0
    
    for webhook_url in webhooks:
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 204:
                success_count += 1
                logger.info(f"✅ Discord 通知已發送 (Webhook {webhooks.index(webhook_url) + 1})")
            else:
                logger.warning(f"⚠️ Discord 回應 {response.status_code}: {response.text[:100]}")
                
        except requests.RequestException as e:
            logger.error(f"❌ Discord 發送失敗: {e}")
    
    return success_count > 0


def check_and_alert(data: Dict[str, Any]) -> int:
    """
    檢查數據並發送相應警報
    
    Args:
        data: 來自 main.py 的快照數據 (包含 cex_flows)
    
    Returns:
        發送的警報數量
    """
    alerts_sent = 0
    
    cex_data = data.get('cex_flows', {})
    summary = cex_data.get('summary', {})
    exchanges = cex_data.get('exchanges', [])
    
    total_stablecoin_flow = summary.get('total_stablecoin_flow_24h', 0)
    total_btc_eth_flow = summary.get('total_btc_eth_flow_24h', 0)
    
    # 使用台灣時間 (UTC+8)
    tz = timezone(timedelta(hours=8))
    timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S (UTC+8)')
    
    # 1. 穩定幣大量流入 -> Buying Power Alert
    if total_stablecoin_flow > THRESHOLDS['stablecoin_inflow']:
        fields = [
            {
                "name": "💰 金額 (Amount)",
                "value": f"${total_stablecoin_flow / 1e6:,.1f}M",
                "inline": True
            },
            {
                "name": "📍 來源 (Source)",
                "value": "所有 CEX 加總",
                "inline": True
            },
            {
                "name": "⏰ 時間 (Time)",
                "value": timestamp,
                "inline": True
            }
        ]
        
        # 添加前 3 大交易所明細
        top_exchanges = []
        for ex in exchanges[:5]:
            if ex.get('stablecoin_flow_24h', 0) > 0:
                top_exchanges.append(
                    f"• {ex['exchange']}: ${ex['stablecoin_flow_24h']/1e6:+.1f}M"
                )
        
        if top_exchanges:
            fields.append({
                "name": "🏦 前三大交易所 (Top Exchanges)",
                "value": "\n".join(top_exchanges[:3]),
                "inline": False
            })
        
        # 生成深度分析
        insight = generate_insight('Bullish_Stablecoin', total_stablecoin_flow)
        
        description = (
            f"**穩定幣流入: ${total_stablecoin_flow / 1e6:,.1f}M**\n\n"
            f"💡 **重點分析:** {insight}\n\n"
            f"🔗 **相關連結:**\n"
            f"• [💎 加密貨幣即時戰情室 (Live Monitor)](https://huyuyuan1989-oss.github.io/cexdex/reports/monitor.html)\n"
            f"• [💰 全鏈資金流向總站 (Main Terminal)]({DASHBOARD_URL})\n"
            f"• [📄 完整數據報告 (Full Report)](https://huyuyuan1989-oss.github.io/cexdex/reports/index.html)\n"
            f"• [📊 原始數據源 (Raw JSON)](https://huyuyuan1989-oss.github.io/cexdex/reports/data.json)"
        )
        
        success = send_discord_alert(
            title="🟢 購買力警報 (Buying Power)",
            message=description,
            color=COLORS['green'],
            fields=fields
        )
        
        if success:
            alerts_sent += 1
    
    # 2. BTC/ETH 大量流入 -> Dump Risk Alert
    if total_btc_eth_flow > THRESHOLDS['btc_eth_inflow']:
        fields = [
            {
                "name": "💰 金額 (Amount)",
                "value": f"${total_btc_eth_flow / 1e6:,.1f}M",
                "inline": True
            },
            {
                "name": "📍 來源 (Source)",
                "value": "所有 CEX 加總",
                "inline": True
            },
            {
                "name": "⏰ 時間 (Time)",
                "value": timestamp,
                "inline": True
            }
        ]
        
        # 添加前 3 大交易所明細
        top_exchanges = []
        for ex in exchanges[:5]:
            if ex.get('btc_eth_flow_24h', 0) > 0:
                top_exchanges.append(
                    f"• {ex['exchange']}: ${ex['btc_eth_flow_24h']/1e6:+.1f}M"
                )
        
        if top_exchanges:
            fields.append({
                "name": "🏦 前三大交易所 (Top Exchanges)",
                "value": "\n".join(top_exchanges[:3]),
                "inline": False
            })
        
        # 生成深度分析
        insight = generate_insight('Bearish_Dump', total_btc_eth_flow)
        
        description = (
            f"**BTC/ETH 流入: ${total_btc_eth_flow / 1e6:,.1f}M**\n\n"
            f"💡 **重點分析:** {insight}\n\n"
            f"🔗 **相關連結:**\n"
            f"• [💎 加密貨幣即時戰情室 (Live Monitor)](https://huyuyuan1989-oss.github.io/cexdex/reports/monitor.html)\n"
            f"• [💰 全鏈資金流向總站 (Main Terminal)]({DASHBOARD_URL})\n"
            f"• [📄 完整數據報告 (Full Report)](https://huyuyuan1989-oss.github.io/cexdex/reports/index.html)\n"
            f"• [📊 原始數據源 (Raw JSON)](https://huyuyuan1989-oss.github.io/cexdex/reports/data.json)"
        )
        
        success = send_discord_alert(
            title="🔴 拋售風險警報 (Dump Risk)",
            message=description,
            color=COLORS['red'],
            fields=fields
        )
        
        if success:
            alerts_sent += 1
    
    # 3. 如果沒有觸發警報，記錄日誌
    if alerts_sent == 0:
        logger.info(f"📊 資金流向正常：穩定幣 ${total_stablecoin_flow/1e6:+.1f}M, "
                   f"BTC/ETH ${total_btc_eth_flow/1e6:+.1f}M (閾值 $100M)")
    
    return alerts_sent


def send_summary_notification(data: Dict[str, Any]) -> bool:
    """
    發送每日/每次執行摘要通知
    
    Args:
        data: 來自 main.py 的快照數據
    """
    # V2 Schema Compatibility
    if 'market_overview' in data:
        sentiment = data['market_overview'].get('sentiment', {}).get('label', 'Unknown')
        stablecoin_cap = data['market_overview'].get('stablecoin_marketcap', 0)
        
        # 4H Data
        cex_flow_4h = data.get('timeframes', {}).get('4h', {}).get('cex', {}).get('net_flow', 0)
    else:
        # Fallback to V1
        sentiment = data.get('market_sentiment', 'Unknown')
        stablecoin_cap = data.get('stablecoin_marketcap', 0)
        cex_flow_4h = 0
    
    chain_summary = data.get('chain_flows', {}).get('summary', {})
    cex_summary = data.get('cex_flows', {}).get('summary', {})
    
    # 根據情緒選擇顏色
    if 'Bullish' in sentiment:
        color = COLORS['green']
    elif 'Bearish' in sentiment:
        color = COLORS['red']
    else:
        color = COLORS['yellow']
    
    fields = [
        {
            "name": "📊 市場情緒",
            "value": sentiment,
            "inline": True
        },
        {
            "name": "💵 穩定幣總市值",
            "value": f"${stablecoin_cap / 1e9:.1f}B",
            "inline": True
        },
        {
            "name": "🔗 公鏈信號",
            "value": f"📈 {chain_summary.get('bullish_signals', 0)} 看漲 | "
                    f"📉 {chain_summary.get('bearish_signals', 0)} 看跌",
            "inline": True
        },
        {
            "name": "🏦 CEX 淨流向 (24H)",
            "value": f"${cex_summary.get('total_net_flow_24h', 0) / 1e6:+.1f}M",
            "inline": True
        },
        {
            "name": "⏱️ CEX 淨流向 (4H/短期)",
            "value": f"${cex_flow_4h / 1e6:+.1f}M",
            "inline": True
        },
        {
            "name": "💰 穩定幣流向 (24H)",
            "value": f"${cex_summary.get('total_stablecoin_flow_24h', 0) / 1e6:+.1f}M",
            "inline": True
        }
    ]
    
    return send_discord_alert(
        title="📡 資金流向監控報告",
        message=(
            f"**{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M (UTC+8)')} 執行完成**\n\n"
            f"🔗 **相關連結:**\n"
            f"• [💎 加密貨幣即時戰情室 (Live Monitor)](https://huyuyuan1989-oss.github.io/cexdex/reports/index.html?tab=monitor)\n"
            f"• [💰 全鏈資金流向總站 (Main Terminal)]({DASHBOARD_URL})\n"
            f"• [📊 原始數據源 (Raw JSON)](https://huyuyuan1989-oss.github.io/cexdex/reports/data.json)"
        ),
        color=color,
        fields=fields
    )


# ================= 測試入口 =================

def test():
    """測試 Discord 通知發送"""
    print("=" * 60)
    print("🧪 Discord 通知服務測試")
    print("=" * 60)
    
    # 測試 1: 發送簡單 Embed
    print("\n[1/2] 測試發送 Embed...")
    success = send_discord_alert(
        title="🧪 測試通知",
        message="這是一條測試訊息，確認 Discord Webhook 正常運作。",
        color=COLORS['blue'],
        fields=[
            {"name": "模組", "value": "notification_service.py", "inline": True},
            {"name": "狀態", "value": "✅ 正常", "inline": True}
        ]
    )
    print(f"   {'✅ 發送成功' if success else '❌ 發送失敗'}")
    
    # 測試 2: 模擬 check_and_alert
    print("\n[2/2] 測試警報邏輯 (模擬數據)...")
    mock_data = {
        'market_sentiment': 'Bullish',
        'stablecoin_marketcap': 300_000_000_000,
        'chain_flows': {'summary': {'bullish_signals': 5, 'bearish_signals': 1}},
        'cex_flows': {
            'summary': {
                'total_stablecoin_flow_24h': 150_000_000,  # $150M - 觸發
                'total_btc_eth_flow_24h': 50_000_000,      # $50M - 不觸發
                'total_net_flow_24h': 200_000_000
            },
            'exchanges': [
                {'exchange': 'binance-cex', 'stablecoin_flow_24h': 100_000_000, 'btc_eth_flow_24h': 30_000_000},
                {'exchange': 'okx', 'stablecoin_flow_24h': 50_000_000, 'btc_eth_flow_24h': 20_000_000}
            ]
        }
    }
    
    alerts = check_and_alert(mock_data)
    print(f"   發送了 {alerts} 個警報")
    
    print("\n" + "=" * 60)
    print("🎉 測試完成")
    print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test()
