#!/bin/bash

# 全鏈資金流向監控系統 - VPS 一鍵安裝腳本
# 適用於 Ubuntu 20.04/22.04 LTS

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🚀 開始安裝全鏈資金流向監控系統...${NC}"

# 1. 獲取腳本所在目錄
WORK_DIR=$(pwd)
echo -e "📂 安裝目錄: ${WORK_DIR}"

# 2. 更新系統 & 安裝 Python 依賴
echo -e "${GREEN}📦 更新系統與安裝 Python...${NC}"
apt update
apt install -y python3 python3-pip python3-venv nginx

# 3. 建立 Python 虛擬環境
echo -e "${GREEN}🐍 建立虛擬環境...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# 4. 啟用環境並安裝依賴
echo -e "${GREEN}📥 安裝程式依賴 (requirements.txt)...${NC}"
source venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo -e "${RED}❌ 找不到 requirements.txt！正在自動安裝默認依賴...${NC}"
    pip install requests aiohttp pandas tabulate colorama Jinja2
fi

# 5. 生成 Systemd 服務文件 (自動開機執行)
SERVICE_FILE="/etc/systemd/system/chain_monitor.service"
echo -e "${GREEN}⚙️ 配置 Systemd 服務 (${SERVICE_FILE})...${NC}"

cat > ${SERVICE_FILE} <<EOF
[Unit]
Description=Chain Money Flow Monitor Service
After=network.target

[Service]
WorkingDirectory=${WORK_DIR}
ExecStart=${WORK_DIR}/venv/bin/python ${WORK_DIR}/full_chain_monitor.py
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 6. 配置 Nginx 以便查看 HTML 報告 (可選)
echo -e "${GREEN}🌐 配置 Nginx 網頁報告查看...${NC}"
# 確保報告目錄存在
mkdir -p reports
# 給予 Nginx 读取全限 (注意安全)
chmod 755 ${WORK_DIR}
chmod 755 ${WORK_DIR}/reports
# 建立軟連結
rm -rf /var/www/html/reports
ln -s ${WORK_DIR}/reports /var/www/html/reports

# 7. 啟動服務
echo -e "${GREEN}🔥 啟動服務中...${NC}"
systemctl daemon-reload
systemctl enable chain_monitor
systemctl restart chain_monitor
systemctl restart nginx

echo -e "
${GREEN}✅ 安裝完成！${NC}

🔍 狀態檢查: systemctl status chain_monitor
📜 查看日誌: journalctl -u chain_monitor -f
📊 網頁報告: http://$(curl -s ifconfig.me)/reports/

程式現在將在後台 24 小時運行，您可以安全地關閉此視窗。
"
