# 🦷 Dental Literature Tracker System | 口腔医学文献追踪系统

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/platform-Web-orange.svg" alt="Platform">
</p>

<p align="center">
  <b>English</b> | <a href="#中文文档">中文</a>
</p>

---

## 📋 Project Overview

**Dental Literature Tracker** is an intelligent web-based system designed for dental researchers and professionals to efficiently track, analyze, and manage the latest dental literature from PubMed. The system leverages advanced AI models to provide automated literature analysis, relevance scoring, and professional terminology extraction.

### Key Purpose
- **Literature Discovery**: Automatically search and retrieve the latest dental research papers from major dental journals
- **AI-Powered Analysis**: Utilize multiple LLM models for intelligent paper analysis and method summarization
- **Research Management**: Organize, filter, and export research findings with customizable journal lists
- **Knowledge Base**: Build and maintain a glossary of professional dental terminology

---

## ✨ Features

### Core Features

| Feature | Description |
|---------|-------------|
| 🔍 **Advanced PubMed Search** | Search across multiple dental journals with customizable time periods |
| 🤖 **Multi-Model AI Integration** | Support for DeepSeek, Qwen, Kimi, GLM, MiniMax, Doubao |
| 📊 **Intelligent Scoring** | Pre-analysis scoring system with risk assessment |
| 📚 **Journal Management** | 14 default dental journals + NCS core journals + Bone research journals |
| 💾 **Glossary System** | Auto-generated English-Chinese terminology glossary |
| 📤 **Export Functionality** | Export research findings in Markdown format |
| 🎯 **Taste Profile** | Personalized research preference management |
| 📱 **Responsive Design** | Works on desktop, tablet, and mobile devices |

---

## 🛠 Prerequisites

### System Requirements
- Modern web browser (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- Internet connection for PubMed API and LLM API access
- No backend server installation required (pure frontend application)

### API Keys Required
- **AI Model API Key** (choose one or more):
  - [DeepSeek](https://platform.deepseek.com/)
  - [Qwen (通义千问)](https://dashscope.aliyun.com/)
  - [Kimi (Moonshot)](https://platform.moonshot.cn/)
  - [GLM (智谱AI)](https://open.bigmodel.cn/)
  - [MiniMax](https://www.minimaxi.com/)
  - [Doubao (豆包)](https://www.volcengine.com/product/doubao)
- **PubMed API**: No key required - public access

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/LinNanzhen/DailyResearch_upgrade.git
cd DailyResearch_upgrade
```

### 2. Open in Browser

**Option A: Direct Open**
Simply double-click `index.html` in your file explorer

**Option B: Local Server (Recommended)**
```bash
# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000

# Node.js
npx serve .

# PHP
php -S localhost:8000
```
Then visit: `http://localhost:8000`

### 3. Online Access

Visit the live demo: **[https://linnanzhen.github.io/DailyResearch_upgrade/](https://linnanzhen.github.io/DailyResearch_upgrade/)**

---

## ⚙️ Configuration

### Settings Panel

1. Click **Settings** button (top-right corner)
2. Configure the following options:

| Setting | Description |
|---------|-------------|
| **AI Model** | Select your preferred LLM provider |
| **API Key** | Your authentication token (stored locally) |
| **Journal List** | Customize which journals to search |
| **Search Strategy** | Enable NCS journals and two-stage analysis |

### Security Note

```
✅ API Keys are stored ONLY in browser's localStorage
✅ Keys are NEVER sent to any external server besides the AI provider
✅ Each browser/device stores keys independently
✅ No backend server means no data collection
```

---

## 📖 Usage Instructions

### Basic Workflow

```
Configure Settings → Enter API Key → Save
         ↓
Select Time Period (1 day / 3 days / 1 week / 1 month)
         ↓
Click "Start" to begin search
         ↓
Monitor Progress with real-time indicators
         ↓
Review Results with AI analysis and scoring
         ↓
Use Features (Glossary / Export / Filter / Taste)
```

### Key Features

#### 📚 Glossary
View extracted English-Chinese terminology with professional translations

#### 🎯 Taste Profile
Manage your research preferences to get more relevant recommendations

#### 📤 Export
Download results in Markdown format for further analysis or reporting

#### 🔖 Filter
Filter papers by journal using the tag buttons at the top

---

## 📊 Default Journal List

### Core Dental Journals (14)

| Journal Name | Impact Focus |
|--------------|--------------|
| International Journal of Oral Science | Comprehensive oral research |
| Journal of Dentistry | General dentistry |
| Clinical Oral Implants Research | Implantology |
| Oral Oncology | Oral cancer research |
| Journal of Clinical Periodontology | Periodontics |
| Journal of Dental Research | Dental sciences |
| Journal of Periodontology | Periodontal research |
| Journal of Endodontics | Endodontics |
| Journal of Prosthodontic Research | Prosthodontics |
| Journal of Oral Rehabilitation | Oral rehabilitation |
| Community Dentistry and Oral Epidemiology | Public health |
| Caries Research | Dental caries |
| Journal of Prosthodontics | Prosthodontics |
| Dental Materials | Biomaterials |

### NCS Core Journals (Nature/Cell/Science Family)
- Nature, Cell, Science, Nature Medicine, Nature Communications, etc.

### Bone Research Journals
- Bone, Bone Research, Journal of Bone and Mineral Research

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│         (HTML5 + CSS3 + Vanilla JavaScript)              │
├─────────────────────────────────────────────────────────┤
│                      Core Modules                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ PubMed API  │  │ AI Analysis │  │  Data Storage   │  │
│  │   Client    │  │   Engine    │  │   (localStorage)│  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                   External APIs                          │
│         PubMed E-Utilities | LLM Provider APIs           │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

- **Frontend**: Pure HTML5, CSS3, JavaScript (ES6+)
- **Styling**: Custom CSS with responsive design
- **APIs**: PubMed E-Utilities API, RESTful AI APIs
- **Storage**: Browser localStorage
- **No Build Step**: Direct browser execution

---

## 📝 API Reference

### PubMed E-Utilities

This project uses the following PubMed APIs:
- `esearch.fcgi` - Search for article IDs
- `esummary.fcgi` - Fetch article summaries
- `efetch.fcgi` - Fetch full article details

Rate limits: 3 requests per second (no API key required)

### AI Model APIs

Supports OpenAI-compatible API format:
```javascript
{
  "model": "model-name",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ]
}
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [PubMed](https://pubmed.ncbi.nlm.nih.gov/) - For providing the literature database
- [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) - For the search API
- All supported LLM providers for their AI capabilities

---

<p align="center">
  Made with ❤️ for dental researchers worldwide
</p>

