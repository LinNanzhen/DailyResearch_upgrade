<script>
// ============ Configuration ============
const DEFAULT_JOURNALS = [
  "International Journal of Oral Science",
  "Journal of Dentistry",
  "Clinical Oral Implants Research",
  "Clinical Implant Dentistry and Related Research",
  "Oral Oncology",
  "Journal of Clinical Periodontology",
  "Journal of Dental Research",
  "Journal of Prosthodontic Research",
  "Periodontology 2000",
  "Journal of Periodontal Research",
  "Journal of Periodontology",
  "Journal of Endodontics",
  "International Endodontic Journal",
  "Dental Materials"
];

const NCS_CORE_JOURNALS = [
  "Nature Medicine",
  "Nature Biomedical Engineering",
  "Nature Communications",
  "Cell",
  "Cell Reports Medicine",
  "Med",
  "Science",
  "Science Translational Medicine",
  "Science Advances"
];

const BONE_CORE_JOURNALS = [
  "Bone",
  "Bone Research",
  "Journal of Bone and Mineral Research",
  "Calcified Tissue International",
  "Osteoporosis International"
];

const CN_JOURNALS = [
  { name: "实用口腔医学杂志", cnki: "https://navi.cnki.net/knavi/journals/SYKO/detail", wanfang: "https://d.wanfangdata.com.cn/periodical/syqkyx" },
  { name: "中华口腔医学杂志", cnki: "https://navi.cnki.net/knavi/journals/ZHKQ/detail", wanfang: "https://d.wanfangdata.com.cn/periodical/zhkqyx" },
  { name: "口腔医学研究", cnki: "https://navi.cnki.net/knavi/journals/KQYZ/detail", wanfang: "https://d.wanfangdata.com.cn/periodical/kqyxyj" },
  { name: "华西口腔医学杂志", cnki: "https://navi.cnki.net/knavi/journals/HXKQ/detail", wanfang: "https://d.wanfangdata.com.cn/periodical/hxkqyxzz" }
];

const MODEL_CONFIG = {
  deepseek: { name: "DeepSeek", url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  qwen: { name: "Qwen", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  kimi: { name: "Kimi", url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  kimi_code: { name: "Kimi Code", url: "https://api.moonshot.cn/v1", model: "kimi-k2-0711-preview" },
  glm: { name: "GLM", url: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
  minimax: { name: "MiniMax", url: "https://api.minimax.chat/v1/text/chatcompletion_v2", model: "MiniMax-Text-01" },
  doubao: { name: "Doubao", url: "https://ark.cn-beijing.volces.com/api/v3", model: "" }
};

const SETTINGS_KEY = "dental_lit_settings";
const TASTE_STORAGE_KEY = "dental_taste_profile";
const DEFAULT_CANDIDATE_CAP = 20;
const SEARCH_CONCURRENCY = 2;
const NORMAL_RETMAX = 6;
const NCS_RETMAX = 10;
const BONE_RETMAX = 10;
const HARD_CANDIDATE_LIMIT = 120;
const ANALYSIS_DELAY_MS = 380;
const REQUEST_TIMEOUT_MS = 18000;
const EUTILS_MIN_INTERVAL_MS = 380;
const EUTILS_MAX_RETRIES = 3;
const LLM_MAX_RETRIES = 2;
const STRICT_MEDICAL_ONLY = true;
const MEDICAL_SIGNAL_KEYWORDS = [
  "oral", "dental", "dentistry", "periodont", "endodont", "implant", "orthodont", "prosthodont",
  "medicine", "medical", "clinical", "patient", "therapy", "treatment", "disease", "diagnosis",
  "oncology", "caries", "gingiva", "maxillofacial", "stomatology", "trial", "biomedical", "translational",
  "免疫", "炎症", "肿瘤", "临床", "患者", "治疗", "诊断", "口腔", "牙", "牙周", "种植", "正畸", "修复"
];

const BONE_PRIORITY_KEYWORDS = [
  "bone", "osseous", "osseointegration", "osteogenesis", "osteoblast", "osteoclast", "osteocyte",
  "mineralization", "bone marrow", "alveolar bone", "mandible", "maxilla", "craniofacial",
  "骨", "骨组织", "成骨", "破骨", "骨再生", "骨修复", "骨愈合", "骨代谢", "牙槽骨", "颌骨"
];

// ============ State ============
let articles = [];
let glossaryTerms = {};
let searchAborted = false;
let currentFilter = "all";
let analyzedCount = 0;
let showAllCandidates = false;
let tasteProfile = null;
let nextEutilsAllowedAt = 0;

// ============ Settings ============
function loadSettings() {
  const s = JSON.parse(localStorage.getItem('dental_lit_settings') || '{}');
  document.getElementById('aiModel').value = s.aiModel || 'deepseek';
  document.getElementById('apiKey').value = s.apiKey || '';
  document.getElementById('modelName').value = s.modelName || '';
  document.getElementById('apiBaseUrl').value = s.apiBaseUrl || '';
  document.getElementById('doubaoEndpoint').value = s.doubaoEndpoint || '';
  document.getElementById('journalList').value = (s.journals || DEFAULT_JOURNALS).join('\n');
  onModelChange();
}

function saveSettings() {
  const journals = document.getElementById('journalList').value.split('\n').map(j => j.trim()).filter(Boolean);
  const settings = {
    aiModel: document.getElementById('aiModel').value,
    apiKey: document.getElementById('apiKey').value,
    modelName: document.getElementById('modelName').value,
    apiBaseUrl: document.getElementById('apiBaseUrl').value,
    doubaoEndpoint: document.getElementById('doubaoEndpoint').value,
    journals: journals.length > 0 ? journals : DEFAULT_JOURNALS
  };
  localStorage.setItem('dental_lit_settings', JSON.stringify(settings));
  showToast('设置已保存', 'success');
  closeSettings();
}

function getSettings() {
  return JSON.parse(localStorage.getItem('dental_lit_settings') || '{}');
}

function resetJournals() {
  document.getElementById('journalList').value = DEFAULT_JOURNALS.join('\n');
}

function onModelChange() {
  const model = document.getElementById('aiModel').value;
  const cfg = MODEL_CONFIG[model];
  document.getElementById('modelHint').textContent = '默认: ' + (cfg.model || '需要填写 Endpoint ID');
  document.getElementById('urlHint').textContent = '默认: ' + cfg.url;
  document.getElementById('doubaoEndpoint').parentElement.style.display = model === 'doubao' ? 'block' : 'none';
}

function openSettings() { document.getElementById('settingsOverlay').classList.add('active'); }
function closeSettings() { document.getElementById('settingsOverlay').classList.remove('active'); }

// ============ PubMed API ============
async function searchPubMed(journal, dateFrom, dateTo) {
  const query = `"${journal}"[Journal] AND ("${dateFrom}"[Date - Publication] : "${dateTo}"[Date - Publication])`;
  const searchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=50&retmode=json`;

  const resp = await fetch(searchUrl);
  if (!resp.ok) throw new Error(`PubMed search failed: ${resp.status}`);
  const data = await resp.json();
  const ids = data.esearchresult?.idlist || [];
  if (ids.length === 0) return [];

  // Fetch details
  const fetchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${ids.join(',')}&retmode=xml`;
  const fetchResp = await fetch(fetchUrl);
  if (!fetchResp.ok) throw new Error(`PubMed fetch failed: ${fetchResp.status}`);
  const xmlText = await fetchResp.text();
  return parsePubMedXml(xmlText, journal);
}

function parsePubMedXml(xmlText, journalHint) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, 'text/xml');
  const articleNodes = doc.querySelectorAll('PubmedArticle');
  const results = [];

  articleNodes.forEach(node => {
    const pmid = node.querySelector('PMID')?.textContent || '';
    const titleNode = node.querySelector('ArticleTitle');
    const title = titleNode?.textContent || 'No title';
    const abstractTexts = node.querySelectorAll('AbstractText');
    let abstract = '';
    abstractTexts.forEach(at => {
      const label = at.getAttribute('Label');
      if (label) abstract += `**${label}**: `;
      abstract += at.textContent + '\n\n';
    });
    abstract = abstract.trim() || 'No abstract available';

    const authors = [];
    node.querySelectorAll('Author').forEach(a => {
      const last = a.querySelector('LastName')?.textContent || '';
      const fore = a.querySelector('ForeName')?.textContent || '';
      if (last) authors.push(`${last} ${fore}`.trim());
    });

    const journal = node.querySelector('Journal Title')?.textContent
      || node.querySelector('ISOAbbreviation')?.textContent
      || journalHint;
    const journalFull = node.querySelector('MedlineJournalInfo JournalTitle')?.textContent || journal;

    // Try to get full journal name from MedlineTA
    const medlineTA = node.querySelector('MedlineTA')?.textContent || '';

    const year = node.querySelector('PubDate Year')?.textContent
      || node.querySelector('PubDate MedlineDate')?.textContent || '';
    const month = node.querySelector('PubDate Month')?.textContent || '';
    const day = node.querySelector('PubDate Day')?.textContent || '';
    const pubDate = [year, month, day].filter(Boolean).join('-');

    const keywords = [];
    node.querySelectorAll('Keyword').forEach(kw => {
      keywords.push(kw.textContent);
    });

    const meshTerms = [];
    node.querySelectorAll('MeshHeading DescriptorName').forEach(m => {
      const text = (m.textContent || '').trim();
      if (text) meshTerms.push(text);
    });

    const publicationTypes = [];
    node.querySelectorAll('PublicationType').forEach(pt => {
      const text = (pt.textContent || '').trim();
      if (text) publicationTypes.push(text);
    });

    const doi = (() => {
      const ids = node.querySelectorAll('ArticleId');
      for (const id of ids) {
        if (id.getAttribute('IdType') === 'doi') return id.textContent;
      }
      return '';
    })();

    results.push({
      pmid, title, titleCn: '', abstract, authors: authors.slice(0, 10),
      journal: medlineTA || journalFull || journalHint,
      pubDate, keywords, meshTerms, publicationTypes, doi,
      methodSummary: '', glossary: [], analyzed: false
    });
  });

  return results;
}

// ============ AI Analysis ============
async function callLLM(prompt, systemPrompt) {
  const s = getSettings();
  const modelKey = s.aiModel || 'deepseek';
  const cfg = MODEL_CONFIG[modelKey];
  const apiKey = modelKey === 'kimi_code'
    ? (s.kimiCodeApiKey || s.apiKey)
    : s.apiKey;
  if (!apiKey) throw new Error('请先配置 API Key');

  let baseUrl = s.apiBaseUrl || cfg.url;
  let model = s.modelName || cfg.model;
  let url = baseUrl.replace(/\/$/, '') + '/chat/completions';

  // Special handling for doubao
  if (modelKey === 'doubao') {
    model = s.doubaoEndpoint || model;
    if (!model) throw new Error('豆包模型需要配置 Endpoint ID');
  }

  // Special handling for minimax (different endpoint structure)
  if (modelKey === 'minimax') {
    url = baseUrl.includes('chatcompletion') ? baseUrl : baseUrl.replace(/\/$/, '') + '/chat/completions';
  }

  const body = {
    model: model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: prompt }
    ],
    temperature: 0.3,
    max_tokens: 2000
  };

  let lastErr = null;
  for (let attempt = 0; attempt < LLM_MAX_RETRIES; attempt++) {
    try {
      const resp = await fetchWithTimeout(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify(body)
      }, REQUEST_TIMEOUT_MS);

      if (!resp.ok) {
        const err = await resp.text();
        if (isRetryableStatus(resp.status) && attempt < LLM_MAX_RETRIES - 1) {
          await sleep(400 * (attempt + 1));
          continue;
        }
        throw new Error(`LLM API error (${resp.status}): ${err.substring(0, 200)}`);
      }

      const data = await resp.json();
      return data.choices?.[0]?.message?.content || '';
    } catch (err) {
      lastErr = err;
      if (attempt < LLM_MAX_RETRIES - 1) {
        await sleep(400 * (attempt + 1));
        continue;
      }
    }
  }
  throw new Error(`LLM request failed after retries: ${lastErr?.message || "unknown error"}`);
}

async function analyzeArticle(article) {
  const systemPrompt = `你是一位口腔医学文献分析专家。请根据提供的论文信息进行分析。
请严格按照以下JSON格式返回结果（不要包含markdown代码块标记）：
{
  "titleCn": "中文标题翻译",
  "methodSummary": "主要内容和研究方法概要（2-3句话，中文）",
  "glossary": [{"en": "English term", "cn": "中文术语"}, ...]
}

注意：
- glossary中只需包含口腔医学相关的专业术语（5-10个）
- methodSummary应概括研究目的、方法和主要发现`;

  const userPrompt = `请分析以下口腔医学论文：

标题: ${article.title}
期刊: ${article.journal}
关键词: ${article.keywords.join(', ')}
摘要: ${article.abstract}`;

  const result = await callLLM(userPrompt, systemPrompt);

  // Parse JSON from response
  try {
    const cleaned = result.replace(/```json?\n?/g, '').replace(/```/g, '').trim();
    const parsed = JSON.parse(cleaned);
    return parsed;
  } catch (e) {
    // Try to extract JSON from the text
    const match = result.match(/\{[\s\S]*\}/);
    if (match) {
      try { return JSON.parse(match[0]); } catch (e2) { /* fall through */ }
    }
    return { titleCn: '', methodSummary: '解析失败: ' + result.substring(0, 100), glossary: [] };
  }
}

// ============ Main Search ============
async function startSearch() {
  const s = getSettings();
  const journals = s.journals || DEFAULT_JOURNALS;
  const days = parseInt(document.getElementById('timePeriod').value);

  const dateTo = new Date();
  const dateFrom = new Date();
  dateFrom.setDate(dateTo.getDate() - days);

  const fmt = d => `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')}`;

  articles = [];
  glossaryTerms = {};
  analyzedCount = 0;
  searchAborted = false;
  currentFilter = "all";

  document.getElementById('searchBtn').style.display = 'none';
  document.getElementById('stopBtn').style.display = 'inline-flex';
  document.getElementById('searchProgress').style.display = 'block';
  document.getElementById('statsSection').style.display = 'flex';
  document.getElementById('searchInfo').textContent = '正在检索...';

  const enJournals = journals.filter(j => /^[a-zA-Z]/.test(j));
  const totalSteps = enJournals.length;
  let completedSteps = 0;

  // Search English journals via PubMed
  for (const journal of enJournals) {
    if (searchAborted) break;
    updateProgress(completedSteps, totalSteps, `正在检索: ${journal}`);

    try {
      const results = await searchPubMed(journal, fmt(dateFrom), fmt(dateTo));
      articles.push(...results);
      // Rate limit: small delay between requests
      await new Promise(r => setTimeout(r, 400));
    } catch (err) {
      console.error(`Error searching ${journal}:`, err);
      showToast(`检索 ${journal} 失败: ${err.message}`, 'error');
    }

    completedSteps++;
    updateProgress(completedSteps, totalSteps, `已完成 ${completedSteps}/${totalSteps} 个期刊`);
    updateStats();
    renderResults();
  }

  // Show Chinese journal links
  showCnJournalLinks(days);

  // AI Analysis
  if (s.apiKey && articles.length > 0) {
    document.getElementById('searchInfo').textContent = '正在进行AI分析...';
    for (let i = 0; i < articles.length; i++) {
      if (searchAborted) break;
      if (articles[i].abstract === 'No abstract available') continue;

      updateProgress(i, articles.length, `AI分析中: ${articles[i].title.substring(0, 40)}...`);
      try {
        const analysis = await analyzeArticle(articles[i]);
        articles[i].titleCn = analysis.titleCn || '';
        articles[i].methodSummary = analysis.methodSummary || '';
        articles[i].glossary = analysis.glossary || [];
        articles[i].analyzed = true;
        analyzedCount++;

        // Merge glossary
        (analysis.glossary || []).forEach(term => {
          if (term.en && term.cn) {
            glossaryTerms[term.en.toLowerCase()] = { en: term.en, cn: term.cn, source: articles[i].journal };
          }
        });

        updateStats();
        renderResults();
        // Rate limit
        await new Promise(r => setTimeout(r, 500));
      } catch (err) {
        console.error(`AI analysis error:`, err);
        showToast(`AI分析失败: ${err.message}`, 'error');
        if (err.message.includes('API Key') || err.message.includes('401') || err.message.includes('403')) break;
      }
    }
  } else if (!s.apiKey) {
    showToast('未配置API Key，跳过AI分析', 'info');
  }

  document.getElementById('searchBtn').style.display = 'inline-flex';
  document.getElementById('stopBtn').style.display = 'none';
  document.getElementById('searchProgress').style.display = 'none';
  document.getElementById('searchInfo').textContent = `检索完成：共 ${articles.length} 篇文献，${analyzedCount} 篇已AI分析`;
  updateStats();
  renderResults();

  if (articles.length > 0) {
    showToast(`检索完成，共找到 ${articles.length} 篇文献`, 'success');
  } else {
    showToast('该时间段内未检索到文献，尝试扩大时间范围', 'info');
  }
}

function stopSearch() {
  searchAborted = true;
  showToast('正在停止检索...', 'info');
}

function updateProgress(current, total, text) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressText').textContent = text;
}

function updateStats() {
  document.getElementById('statTotal').textContent = articles.length;
  const journals = new Set(articles.map(a => a.journal));
  document.getElementById('statJournals').textContent = journals.size;
  document.getElementById('statAnalyzed').textContent = analyzedCount;
  document.getElementById('statTerms').textContent = Object.keys(glossaryTerms).length;
}

// ============ Chinese Journal Links ============
function showCnJournalLinks(days) {
  const section = document.getElementById('cnJournalSection');
  const container = document.getElementById('cnJournalLinks');
  section.style.display = 'block';
  container.innerHTML = '';

  CN_JOURNALS.forEach(j => {
    const card = document.createElement('div');
    card.className = 'cn-link-card';
    card.innerHTML = `
      <span class="name">${j.name}</span>
      <span>
        <a href="${j.cnki}" target="_blank">CNKI</a>
        &nbsp;|&nbsp;
        <a href="${j.wanfang}" target="_blank">万方</a>
      </span>`;
    container.appendChild(card);
  });
}

// ============ Rendering ============
function renderResults() {
  const area = document.getElementById('resultsArea');
  if (articles.length === 0) {
    area.innerHTML = '<div class="loading"><div class="spinner"></div><p>正在检索中...</p></div>';
    return;
  }

  // Filter
  const filtered = currentFilter === 'all' ? articles : articles.filter(a => a.journal === currentFilter);

  // Group by journal
  const grouped = {};
  filtered.forEach(a => {
    if (!grouped[a.journal]) grouped[a.journal] = [];
    grouped[a.journal].push(a);
  });

  // Render journal filter
  renderJournalFilter();

  // Render articles
  let html = '';
  Object.keys(grouped).sort().forEach(journal => {
    const arts = grouped[journal];
    html += `<div class="articles-section"><h2>${journal} (${arts.length})</h2>`;
    arts.forEach((a, idx) => {
      const globalIdx = articles.indexOf(a);
      html += renderArticleCard(a, globalIdx);
    });
    html += '</div>';
  });

  area.innerHTML = html;
}

function renderArticleCard(a, idx) {
  const authorsStr = a.authors.length > 3
    ? a.authors.slice(0, 3).join(', ') + ' et al.'
    : a.authors.join(', ');
  const doiLink = a.doi ? `<a href="https://doi.org/${a.doi}" target="_blank" style="color:var(--primary);text-decoration:none">DOI</a>` : '';
  const pmidLink = a.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/" target="_blank" style="color:var(--primary);text-decoration:none">PubMed</a>` : '';

  return `
    <div class="article-card">
      <div class="article-title">${escapeHtml(a.title)}</div>
      ${a.titleCn ? `<div class="article-title-cn">${escapeHtml(a.titleCn)}</div>` : ''}
      <div class="article-meta">
        <span>&#128100; ${escapeHtml(authorsStr)}</span>
        <span>&#128197; ${escapeHtml(a.pubDate)}</span>
        <span>&#128214; ${escapeHtml(a.journal)}</span>
        ${doiLink ? `<span>${doiLink}</span>` : ''}
        ${pmidLink ? `<span>${pmidLink}</span>` : ''}
      </div>
      ${a.keywords.length > 0 ? `
        <div class="article-keywords">
          ${a.keywords.map(k => `<span class="keyword-tag">${escapeHtml(k)}</span>`).join('')}
        </div>` : ''}
      <div class="article-abstract collapsed" id="abstract-${idx}">${escapeHtml(a.abstract)}</div>
      <div class="article-actions">
        <button class="expand-btn" onclick="toggleAbstract(${idx})">展开摘要</button>
        ${a.analyzed ? `<button class="expand-btn" onclick="toggleAnalysis(${idx})">查看AI分析</button>` : ''}
        ${!a.analyzed && a.abstract !== 'No abstract available' ? `<button class="expand-btn" onclick="analyzeOne(${idx})">AI分析此文</button>` : ''}
      </div>
      ${a.analyzed ? `
        <div class="ai-analysis" id="analysis-${idx}">
          <h4>&#129302; AI分析</h4>
          <div class="method-summary">${escapeHtml(a.methodSummary)}</div>
          ${a.glossary.length > 0 ? `
            <table class="glossary-table">
              <thead><tr><th>英文术语</th><th>中文翻译</th></tr></thead>
              <tbody>${a.glossary.map(g => `<tr><td>${escapeHtml(g.en)}</td><td>${escapeHtml(g.cn)}</td></tr>`).join('')}</tbody>
            </table>` : ''}
        </div>` : ''}
    </div>`;
}

function renderJournalFilter() {
  const filterDiv = document.getElementById('journalFilter');
  const tagsDiv = document.getElementById('journalTags');
  if (articles.length === 0) { filterDiv.style.display = 'none'; return; }

  filterDiv.style.display = 'block';
  const counts = {};
  articles.forEach(a => { counts[a.journal] = (counts[a.journal] || 0) + 1; });

  let html = `<span class="journal-tag ${currentFilter === 'all' ? 'active' : ''}" onclick="setFilter('all')">全部<span class="count">(${articles.length})</span></span>`;
  Object.keys(counts).sort().forEach(j => {
    html += `<span class="journal-tag ${currentFilter === j ? 'active' : ''}" onclick="setFilter('${escapeHtml(j)}')">${escapeHtml(j)}<span class="count">(${counts[j]})</span></span>`;
  });
  tagsDiv.innerHTML = html;
}

function setFilter(journal) {
  currentFilter = journal;
  renderResults();
}

function toggleAbstract(idx) {
  const el = document.getElementById('abstract-' + idx);
  if (el) el.classList.toggle('collapsed');
}

function toggleAnalysis(idx) {
  const el = document.getElementById('analysis-' + idx);
  if (el) el.classList.toggle('active');
}

async function analyzeOne(idx) {
  const s = getSettings();
  if (!s.apiKey) { showToast('请先配置API Key', 'error'); return; }

  const a = articles[idx];
  showToast('正在分析...', 'info');
  try {
    const analysis = await analyzeArticle(a);
    articles[idx].titleCn = analysis.titleCn || '';
    articles[idx].methodSummary = analysis.methodSummary || '';
    articles[idx].glossary = analysis.glossary || [];
    articles[idx].analyzed = true;
    analyzedCount++;
    (analysis.glossary || []).forEach(term => {
      if (term.en && term.cn) {
        glossaryTerms[term.en.toLowerCase()] = { en: term.en, cn: term.cn, source: a.journal };
      }
    });
    updateStats();
    renderResults();
    showToast('分析完成', 'success');
  } catch (err) {
    showToast('分析失败: ' + err.message, 'error');
  }
}

// ============ Glossary ============
function showGlossary() {
  const overlay = document.getElementById('glossaryOverlay');
  overlay.classList.add('active');
  const tbody = document.getElementById('glossaryBody');
  const emptyMsg = document.getElementById('glossaryEmpty');
  const terms = Object.values(glossaryTerms).sort((a, b) => a.en.localeCompare(b.en));
  if (terms.length > 0) {
    tbody.innerHTML = terms.map(t => `<tr><td>${escapeHtml(t.en)}</td><td>${escapeHtml(t.cn)}</td><td>${escapeHtml(t.source)}</td></tr>`).join('');
    document.getElementById('glossaryTable').style.display = '';
    emptyMsg.style.display = 'none';
  } else {
    tbody.innerHTML = '';
    document.getElementById('glossaryTable').style.display = 'none';
    emptyMsg.style.display = 'block';
  }
}

function closeGlossary() {
  document.getElementById('glossaryOverlay').classList.remove('active');
}

// ============ Export ============
function exportMarkdown() {
  if (articles.length === 0) { showToast('暂无文献数据可导出', 'error'); return; }

  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const days = document.getElementById('timePeriod').value;
  const periodName = { '1': '日报', '3': '三日报', '7': '周报', '30': '月报' }[days] || '报告';

  let md = `# 口腔医学文献${periodName}\n\n`;
  md += `> 生成日期：${dateStr} | 检索范围：过去${days}天 | 共${articles.length}篇文献\n\n`;
  md += `---\n\n`;

  // Group by journal
  const grouped = {};
  articles.forEach(a => {
    if (!grouped[a.journal]) grouped[a.journal] = [];
    grouped[a.journal].push(a);
  });

  Object.keys(grouped).sort().forEach(journal => {
    md += `## ${journal}\n\n`;
    grouped[journal].forEach((a, i) => {
      md += `### ${i + 1}. ${a.title}\n\n`;
      if (a.titleCn) md += `**中文标题**: ${a.titleCn}\n\n`;
      md += `- **作者**: ${a.authors.join(', ')}\n`;
      md += `- **期刊**: ${a.journal}\n`;
      md += `- **发表日期**: ${a.pubDate}\n`;
      if (a.doi) md += `- **DOI**: [${a.doi}](https://doi.org/${a.doi})\n`;
      if (a.pmid) md += `- **PubMed**: [${a.pmid}](https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/)\n`;
      if (a.keywords.length > 0) md += `- **关键词**: ${a.keywords.join(', ')}\n`;
      md += `\n`;
      md += `**摘要 (Abstract)**:\n\n${a.abstract}\n\n`;
      if (a.methodSummary) md += `**主要内容和方法**:\n\n${a.methodSummary}\n\n`;
      if (a.glossary && a.glossary.length > 0) {
        md += `**专业术语**:\n\n`;
        md += `| 英文 | 中文 |\n|------|------|\n`;
        a.glossary.forEach(g => { md += `| ${g.en} | ${g.cn} |\n`; });
        md += `\n`;
      }
      md += `---\n\n`;
    });
  });

  // Global glossary
  const terms = Object.values(glossaryTerms).sort((a, b) => a.en.localeCompare(b.en));
  if (terms.length > 0) {
    md += `## 专业名词中英文对照表\n\n`;
    md += `| 英文 | 中文 | 来源 |\n|------|------|------|\n`;
    terms.forEach(t => { md += `| ${t.en} | ${t.cn} | ${t.source} |\n`; });
    md += `\n`;
  }

  // Chinese journal notice
  md += `## 中文期刊\n\n`;
  md += `以下中文期刊请通过 CNKI 或万方数据库手动查阅：\n\n`;
  CN_JOURNALS.forEach(j => {
    md += `- **${j.name}**: [CNKI](${j.cnki}) | [万方](${j.wanfang})\n`;
  });

  // Download
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `口腔文献${periodName}_${dateStr}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('报告已下载', 'success');
}

// ============ Utils ============
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function mergeUnique(base, extra) {
  const out = [];
  const seen = new Set();
  [...(base || []), ...(extra || [])].forEach(item => {
    const text = String(item || "").trim();
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  });
  return out;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function waitForEutilsSlot() {
  const now = Date.now();
  const waitMs = Math.max(0, nextEutilsAllowedAt - now);
  if (waitMs > 0) await sleep(waitMs);
  nextEutilsAllowedAt = Date.now() + EUTILS_MIN_INTERVAL_MS;
}

function isRetryableStatus(status) {
  return status === 429 || status >= 500;
}

async function eutilsRequest(url, parseAs = "json") {
  let lastErr = null;
  for (let attempt = 0; attempt < EUTILS_MAX_RETRIES; attempt++) {
    try {
      await waitForEutilsSlot();
      const resp = await fetchWithTimeout(url, {}, REQUEST_TIMEOUT_MS);
      if (!resp.ok) {
        if (isRetryableStatus(resp.status) && attempt < EUTILS_MAX_RETRIES - 1) {
          await sleep(500 * (attempt + 1));
          continue;
        }
        throw new Error(`HTTP ${resp.status}`);
      }
      return parseAs === "text" ? await resp.text() : await resp.json();
    } catch (err) {
      lastErr = err;
      if (attempt < EUTILS_MAX_RETRIES - 1) {
        await sleep(500 * (attempt + 1));
        continue;
      }
    }
  }
  throw new Error(`PubMed request failed after ${EUTILS_MAX_RETRIES} retries: ${lastErr?.message || "unknown error"}`);
}

function createDefaultTasteProfile() {
  return {
    journalBias: {},
    topicWeights: {},
    methodWeights: {},
    negativePatterns: {},
    updatedAt: new Date().toISOString()
  };
}

function normalizeWeightMap(obj) {
  const out = {};
  if (!obj || typeof obj !== "object") return out;
  Object.entries(obj).forEach(([k, v]) => {
    const key = String(k || "").trim().toLowerCase();
    const num = Number(v);
    if (!key || !Number.isFinite(num)) return;
    out[key] = clamp(num, -50, 50);
  });
  return out;
}

function normalizeTasteProfile(raw) {
  const base = createDefaultTasteProfile();
  if (!raw || typeof raw !== "object") return base;
  return {
    journalBias: normalizeWeightMap(raw.journalBias),
    topicWeights: normalizeWeightMap(raw.topicWeights),
    methodWeights: normalizeWeightMap(raw.methodWeights),
    negativePatterns: normalizeWeightMap(raw.negativePatterns),
    updatedAt: raw.updatedAt || base.updatedAt
  };
}

function loadTasteProfile() {
  try {
    tasteProfile = normalizeTasteProfile(JSON.parse(localStorage.getItem(TASTE_STORAGE_KEY) || "{}"));
  } catch {
    tasteProfile = createDefaultTasteProfile();
  }
}

function persistTasteProfile() {
  tasteProfile.updatedAt = new Date().toISOString();
  localStorage.setItem(TASTE_STORAGE_KEY, JSON.stringify(tasteProfile));
}

function tasteToMarkdown(profile) {
  return [
    "# taste.md",
    "",
    `UpdatedAt: ${profile.updatedAt || new Date().toISOString()}`,
    "",
    "```json",
    JSON.stringify(profile, null, 2),
    "```",
    ""
  ].join("\n");
}

function parseTasteMarkdown(text) {
  const src = String(text || "").trim();
  if (!src) throw new Error("taste.md 内容为空");
  const block = src.match(/```json\s*([\s\S]*?)```/i);
  const payload = block ? block[1] : (() => {
    const m = src.match(/\{[\s\S]*\}/);
    if (!m) throw new Error("未找到 JSON 内容");
    return m[0];
  })();
  return normalizeTasteProfile(JSON.parse(payload));
}

function openTasteManager() {
  refreshTasteEditor();
  document.getElementById("tasteOverlay").classList.add("active");
}

function closeTasteManager() {
  document.getElementById("tasteOverlay").classList.remove("active");
}

function refreshTasteEditor() {
  document.getElementById("tasteEditor").value = tasteToMarkdown(tasteProfile || createDefaultTasteProfile());
}

function exportTasteMarkdown() {
  const blob = new Blob([tasteToMarkdown(tasteProfile)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "taste.md";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast("taste.md 已导出", "success");
}

function triggerTasteFileImport() {
  document.getElementById("tasteFileInput").click();
}

function handleTasteFileImport(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById("tasteEditor").value = String(reader.result || "");
    showToast("文件已载入编辑区，请点击“更新 Taste”", "info");
  };
  reader.readAsText(file, "utf-8");
  event.target.value = "";
}

function importTasteFromEditor() {
  try {
    const content = document.getElementById("tasteEditor").value;
    tasteProfile = parseTasteMarkdown(content);
    persistTasteProfile();
    recomputeScoresAndSort();
    renderResults();
    showToast("Taste 已更新", "success");
  } catch (err) {
    showToast(`Taste 更新失败: ${err.message}`, "error");
  }
}

function resetTasteProfile() {
  tasteProfile = createDefaultTasteProfile();
  persistTasteProfile();
  refreshTasteEditor();
  recomputeScoresAndSort();
  renderResults();
  showToast("Taste 已重置", "success");
}

function normalizeSettings(raw) {
  const safe = raw && typeof raw === "object" ? raw : {};
  return {
    aiModel: safe.aiModel || "deepseek",
    apiKey: safe.apiKey || "",
    kimiCodeApiKey: safe.kimiCodeApiKey || "",
    modelName: safe.modelName || "",
    apiBaseUrl: safe.apiBaseUrl || "",
    doubaoEndpoint: safe.doubaoEndpoint || "",
    candidateCap: clamp(parseInt(safe.candidateCap, 10) || DEFAULT_CANDIDATE_CAP, 5, 100),
    enableNcsCore: safe.enableNcsCore !== false,
    twoStageAnalysis: safe.twoStageAnalysis !== false,
    journals: Array.isArray(safe.journals) && safe.journals.length > 0 ? safe.journals : [...DEFAULT_JOURNALS]
  };
}

function withNcsJournals(journals, enableNcsCore) {
  const base = Array.isArray(journals) ? journals : [];
  const withNcs = enableNcsCore ? mergeUnique(base, NCS_CORE_JOURNALS) : [...base];
  return mergeUnique(withNcs, BONE_CORE_JOURNALS);
}

function stripNcsJournals(journals) {
  const ncsLower = new Set(NCS_CORE_JOURNALS.map(j => j.toLowerCase()));
  return (Array.isArray(journals) ? journals : []).filter(j => !ncsLower.has(String(j).toLowerCase()));
}

function getSettings() {
  try {
    return normalizeSettings(JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}"));
  } catch {
    return normalizeSettings({});
  }
}

function loadSettings() {
  const s = getSettings();
  document.getElementById("aiModel").value = s.aiModel;
  document.getElementById("apiKey").value = s.apiKey;
  document.getElementById("kimiCodeApiKey").value = s.kimiCodeApiKey || "";
  document.getElementById("modelName").value = s.modelName;
  document.getElementById("apiBaseUrl").value = s.apiBaseUrl;
  document.getElementById("doubaoEndpoint").value = s.doubaoEndpoint;
  document.getElementById("candidateCap").value = s.candidateCap;
  document.getElementById("enableNcsCore").checked = s.enableNcsCore;
  document.getElementById("twoStageAnalysis").checked = s.twoStageAnalysis;
  document.getElementById("journalList").value = withNcsJournals(s.journals, s.enableNcsCore).join("\n");
  onModelChange();
}

function saveSettings() {
  const enableNcsCore = document.getElementById("enableNcsCore").checked;
  const journalsRaw = document.getElementById("journalList").value.split("\n").map(j => j.trim()).filter(Boolean);
  const journals = enableNcsCore ? withNcsJournals(journalsRaw, true) : stripNcsJournals(journalsRaw);
  const settings = normalizeSettings({
    aiModel: document.getElementById("aiModel").value,
    apiKey: document.getElementById("apiKey").value,
    kimiCodeApiKey: document.getElementById("kimiCodeApiKey").value,
    modelName: document.getElementById("modelName").value,
    apiBaseUrl: document.getElementById("apiBaseUrl").value,
    doubaoEndpoint: document.getElementById("doubaoEndpoint").value,
    candidateCap: parseInt(document.getElementById("candidateCap").value, 10),
    enableNcsCore,
    twoStageAnalysis: document.getElementById("twoStageAnalysis").checked,
    journals: journals.length > 0 ? journals : [...DEFAULT_JOURNALS]
  });
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  document.getElementById("journalList").value = withNcsJournals(settings.journals, settings.enableNcsCore).join("\n");
  showToast("设置已保存", "success");
  closeSettings();
}

function resetJournals() {
  const enableNcsCore = document.getElementById("enableNcsCore").checked;
  document.getElementById("journalList").value = withNcsJournals(DEFAULT_JOURNALS, enableNcsCore).join("\n");
}

function handleNcsToggle() {
  const enableNcsCore = document.getElementById("enableNcsCore").checked;
  const list = document.getElementById("journalList").value.split("\n").map(j => j.trim()).filter(Boolean);
  document.getElementById("journalList").value = (enableNcsCore ? withNcsJournals(list, true) : stripNcsJournals(list)).join("\n");
}

function onModelChange() {
  const model = document.getElementById("aiModel").value;
  const cfg = MODEL_CONFIG[model];
  document.getElementById("modelHint").textContent = "默认: " + (cfg.model || "需要填写 Endpoint ID");
  document.getElementById("urlHint").textContent = "默认: " + cfg.url;
  document.getElementById("doubaoEndpoint").parentElement.style.display = model === "doubao" ? "block" : "none";
  const kimiWrap = document.getElementById("kimiCodeApiKeyWrap");
  if (kimiWrap) kimiWrap.style.display = model === "kimi_code" ? "block" : "none";
}

function isNcsCoreJournal(journal) {
  return NCS_CORE_JOURNALS.some(j => j.toLowerCase() === String(journal || "").toLowerCase());
}

function isBoneCoreJournal(journal) {
  return BONE_CORE_JOURNALS.some(j => j.toLowerCase() === String(journal || "").toLowerCase());
}

function articleTimestamp(article) {
  if (typeof article._ts === "number") return article._ts;
  const raw = String(article.pubDate || "").trim();
  let ts = Date.parse(raw);
  if (!Number.isFinite(ts)) {
    const year = raw.match(/(19|20)\d{2}/)?.[0];
    ts = year ? Date.parse(`${year}-01-01`) : 0;
  }
  article._ts = Number.isFinite(ts) ? ts : 0;
  return article._ts;
}

function dedupeArticles(items) {
  const byKey = new Map();
  items.forEach(a => {
    const key = (a.doi && `doi:${a.doi.toLowerCase()}`) || (a.pmid && `pmid:${a.pmid}`) || `title:${(a.title || "").toLowerCase()}|journal:${(a.journal || "").toLowerCase()}`;
    const old = byKey.get(key);
    if (!old || articleTimestamp(a) > articleTimestamp(old)) byKey.set(key, a);
  });
  return Array.from(byKey.values());
}

function tokenize(text) {
  return String(text || "").toLowerCase().split(/[^a-z0-9\u4e00-\u9fa5]+/).map(x => x.trim()).filter(x => x.length >= 2).slice(0, 50);
}

function hasMedicalSignal(article) {
  const journal = String(article.journal || "").toLowerCase();
  const pool = [
    article.journal || "",
    article.title || "",
    article.abstract || "",
    ...(article.keywords || []),
    ...(article.meshTerms || []),
    ...(article.publicationTypes || [])
  ].join(" ").toLowerCase();

  const journalSignal = /(med|clinic|oncolog|dental|oral|stomat|translat|biomed|patient|therapy|disease)/.test(journal);
  if (journalSignal) return true;

  return MEDICAL_SIGNAL_KEYWORDS.some(k => pool.includes(String(k).toLowerCase()))
    || BONE_PRIORITY_KEYWORDS.some(k => pool.includes(String(k).toLowerCase()));
}

function computeBoneBoost(article) {
  const pool = [
    article.journal || "",
    article.title || "",
    article.abstract || "",
    ...(article.keywords || []),
    ...(article.meshTerms || []),
    ...(article.tags || [])
  ].join(" ").toLowerCase();

  let hitCount = 0;
  BONE_PRIORITY_KEYWORDS.forEach(k => {
    if (pool.includes(String(k).toLowerCase())) hitCount += 1;
  });

  if (hitCount === 0) return 0;
  if (hitCount <= 2) return 2;
  if (hitCount <= 5) return 4;
  return 6;
}

function uniqueLower(items) {
  const set = new Set();
  const out = [];
  (items || []).forEach(item => {
    const key = String(item || "").trim().toLowerCase();
    if (!key || set.has(key)) return;
    set.add(key);
    out.push(key);
  });
  return out;
}

function computeTasteBoost(article) {
  const journalKey = String(article.journal || "").toLowerCase();
  const journalBias = Number((tasteProfile && tasteProfile.journalBias?.[journalKey]) || 0);
  const topicTerms = uniqueLower([...(article.keywords || []), ...tokenize(article.title).slice(0, 12)]);
  const methodTerms = uniqueLower(article.tags || []);
  const topicScore = topicTerms.length === 0 ? 0 : topicTerms.reduce((sum, term) => sum + Number((tasteProfile.topicWeights || {})[term] || 0), 0) / topicTerms.length;
  const methodScore = methodTerms.length === 0 ? 0 : methodTerms.reduce((sum, term) => sum + Number((tasteProfile.methodWeights || {})[term] || 0), 0) / methodTerms.length;
  const negativeCorpus = `${article.title || ""} ${(article.abstract || "").slice(0, 1000)} ${(article.reasonShort || "")} ${(article.tags || []).join(" ")}`.toLowerCase();
  let negativePenalty = 0;
  Object.entries((tasteProfile.negativePatterns || {})).forEach(([pattern, weight]) => {
    if (pattern && negativeCorpus.includes(pattern)) negativePenalty += Math.abs(Number(weight) || 0);
  });
  const raw = (journalBias * 1.3) + topicScore + methodScore - (negativePenalty * 0.8);
  return clamp(50 + raw * 8, 0, 100);
}

function deriveRiskTags(article) {
  const tags = [];
  if (Number(article.routineRisk) >= 70) tags.push("套路化风险高");
  if (Number(article.aimFit) <= 40) tags.push("Aim匹配低");
  return tags;
}

function computePreScore(article) {
  const relevance = clamp(Number(article.relevance) || 50, 0, 100);
  const aimFit = clamp(Number(article.aimFit) || 50, 0, 100);
  const novelty = clamp(Number(article.novelty) || 50, 0, 100);
  const ncsBoost = isNcsCoreJournal(article.journal) ? 4 : 0;
  const boneBoost = computeBoneBoost(article);
  const tasteBoost = computeTasteBoost(article);
  article.tasteBoost = tasteBoost;
  article.ncsBoost = ncsBoost;
  article.boneBoost = boneBoost;
  article.riskTags = deriveRiskTags(article);
  return clamp(Math.round(((0.4 * relevance) + (0.25 * aimFit) + (0.2 * novelty) + (0.15 * tasteBoost) + ncsBoost + boneBoost) * 10) / 10, 0, 100);
}

function recomputeScoresAndSort() {
  articles.forEach(a => { a.preScore = computePreScore(a); });
  articles.sort((a, b) => {
    const diff = (b.preScore || 0) - (a.preScore || 0);
    if (Math.abs(diff) > 0.01) return diff;
    return articleTimestamp(b) - articleTimestamp(a);
  });
}

function ratingToDelta(star) {
  const map = { 1: -3, 2: -1.5, 3: 0, 4: 1.5, 5: 3 };
  return map[star] ?? 0;
}

function adjustWeight(map, key, delta) {
  if (!key) return;
  const next = clamp(Number(map[key] || 0) + delta, -50, 50);
  if (Math.abs(next) < 0.05) delete map[key];
  else map[key] = Math.round(next * 10) / 10;
}

function applyTasteLearning(article, star) {
  const delta = ratingToDelta(star);
  if (delta === 0) return;
  const journalKey = String(article.journal || "").toLowerCase();
  adjustWeight(tasteProfile.journalBias, journalKey, delta);
  uniqueLower([...(article.keywords || []), ...tokenize(article.title).slice(0, 12)]).slice(0, 18).forEach(term => adjustWeight(tasteProfile.topicWeights, term, delta * 0.55));
  uniqueLower(article.tags || []).slice(0, 10).forEach(tag => adjustWeight(tasteProfile.methodWeights, tag, delta * 0.45));
  if (star <= 2) {
    uniqueLower(article.tags || []).slice(0, 6).forEach(tag => adjustWeight(tasteProfile.negativePatterns, tag, Math.abs(delta)));
    tokenize(article.reasonShort || "").slice(0, 6).forEach(term => adjustWeight(tasteProfile.negativePatterns, term, Math.abs(delta) * 0.5));
  }
  if (star >= 4) uniqueLower(article.tags || []).slice(0, 6).forEach(tag => adjustWeight(tasteProfile.negativePatterns, tag, -Math.abs(delta) * 0.6));
  persistTasteProfile();
}

function rateArticle(idx, star) {
  const article = articles[idx];
  if (!article) return;
  article.starRating = star;
  applyTasteLearning(article, star);
  recomputeScoresAndSort();
  renderResults();
  refreshTasteEditor();
  showToast(`已记录 ${star} 星评分，Taste 已更新`, "success");
}

async function searchPubMed(journal, dateFrom, dateTo, retmax = 50) {
  const query = `"${journal}"[Journal] AND ("${dateFrom}"[Date - Publication] : "${dateTo}"[Date - Publication])`;
  const searchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=${retmax}&retmode=json`;
  const data = await eutilsRequest(searchUrl, "json");
  const ids = data.esearchresult?.idlist || [];
  if (ids.length === 0) return [];
  const fetchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${ids.join(",")}&retmode=xml`;
  const xmlText = await eutilsRequest(fetchUrl, "text");
  return parsePubMedXml(xmlText, journal);
}

function extractJsonObject(text) {
  const cleaned = String(text || "").replace(/```json?\n?/gi, "").replace(/```/g, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (match) return JSON.parse(match[0]);
    throw new Error("invalid json");
  }
}

async function preAnalyzeArticle(article) {
  const systemPrompt = `你是医学论文快速分诊助手。请只返回 JSON。字段如下：
{
  "relevance": 0-100,
  "aimFit": 0-100,
  "novelty": 0-100,
  "routineRisk": 0-100,
  "translationalValue": 0-100,
  "reasonShort": "一句话简述是否值得看",
  "tags": ["标签1","标签2"]
}
评估标准：口腔医学优先，同时保留可迁移医学研究；套路化研究给更高 routineRisk。`;
  const userPrompt = `标题: ${article.title}\n期刊: ${article.journal}\n关键词: ${(article.keywords || []).join(", ")}\n摘要: ${String(article.abstract || "").slice(0, 2200)}`;
  const result = await callLLM(userPrompt, systemPrompt);
  const parsed = extractJsonObject(result);
  return {
    relevance: clamp(Number(parsed.relevance) || 50, 0, 100),
    aimFit: clamp(Number(parsed.aimFit) || 50, 0, 100),
    novelty: clamp(Number(parsed.novelty) || 50, 0, 100),
    routineRisk: clamp(Number(parsed.routineRisk) || 50, 0, 100),
    translationalValue: clamp(Number(parsed.translationalValue) || 50, 0, 100),
    reasonShort: String(parsed.reasonShort || "").slice(0, 160),
    tags: Array.isArray(parsed.tags) ? parsed.tags.map(t => String(t).trim()).filter(Boolean).slice(0, 8) : []
  };
}

async function analyzeArticle(article) {
  const systemPrompt = `你是一位口腔医学文献分析专家。请根据提供的论文信息进行分析，严格返回 JSON：
{
  "titleCn": "中文标题翻译",
  "methodSummary": "2-3句话总结研究目的、方法和关键发现",
  "glossary": [{"en":"English term","cn":"中文术语"}]
}
要求：glossary 仅保留口腔医学相关术语（5-10个）。`;
  const userPrompt = `请分析以下论文：\n标题: ${article.title}\n期刊: ${article.journal}\n关键词: ${(article.keywords || []).join(", ")}\n摘要: ${article.abstract}`;
  const result = await callLLM(userPrompt, systemPrompt);
  try {
    const parsed = extractJsonObject(result);
    return {
      titleCn: String(parsed.titleCn || ""),
      methodSummary: String(parsed.methodSummary || ""),
      glossary: Array.isArray(parsed.glossary)
        ? parsed.glossary.map(x => ({ en: String(x.en || "").trim(), cn: String(x.cn || "").trim() })).filter(x => x.en && x.cn).slice(0, 12)
        : []
    };
  } catch {
    return { titleCn: "", methodSummary: "解析失败", glossary: [] };
  }
}

async function mapWithConcurrency(items, limit, worker, progressCb) {
  if (items.length === 0) return [];
  const results = new Array(items.length);
  let nextIndex = 0;
  let completed = 0;

  async function runWorker() {
    while (true) {
      const index = nextIndex++;
      if (index >= items.length || searchAborted) break;
      try {
        results[index] = await worker(items[index], index);
      } catch (err) {
        results[index] = { __error: err };
      }
      completed += 1;
      if (progressCb) progressCb(completed, items.length, items[index], results[index]);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, runWorker));
  return results;
}

async function runDeepAnalysis(targetArticles) {
  for (let i = 0; i < targetArticles.length; i++) {
    if (searchAborted) break;
    const a = targetArticles[i];
    if (a.abstract === "No abstract available") continue;
    updateProgress(i, targetArticles.length, `深度分析: ${a.title.substring(0, 36)}...`);
    try {
      const analysis = await analyzeArticle(a);
      a.titleCn = analysis.titleCn || "";
      a.methodSummary = analysis.methodSummary || "";
      a.glossary = analysis.glossary || [];
      if (!a.analyzed) analyzedCount += 1;
      a.analyzed = true;
      (a.glossary || []).forEach(term => {
        if (term.en && term.cn) glossaryTerms[term.en.toLowerCase()] = { en: term.en, cn: term.cn, source: a.journal };
      });
    } catch (err) {
      console.error("AI analysis error:", err);
      showToast(`AI分析失败: ${err.message}`, "error");
      if (String(err.message).includes("401") || String(err.message).includes("403")) break;
    }
    updateStats();
    renderResults();
    await sleep(ANALYSIS_DELAY_MS);
  }
}

async function startSearch() {
  const s = getSettings();
  const journals = withNcsJournals(s.journals || DEFAULT_JOURNALS, s.enableNcsCore);
  const days = parseInt(document.getElementById("timePeriod").value, 10);
  const cap = clamp(parseInt(s.candidateCap, 10) || DEFAULT_CANDIDATE_CAP, 5, 100);
  const dateTo = new Date();
  const dateFrom = new Date();
  dateFrom.setDate(dateTo.getDate() - days);
  const fmt = d => `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;

  articles = [];
  glossaryTerms = {};
  analyzedCount = 0;
  searchAborted = false;
  currentFilter = "all";
  showAllCandidates = false;

  document.getElementById("searchBtn").style.display = "none";
  document.getElementById("stopBtn").style.display = "inline-flex";
  document.getElementById("searchProgress").style.display = "block";
  document.getElementById("statsSection").style.display = "flex";
  document.getElementById("searchInfo").textContent = "正在检索文献...";

  const enJournals = journals.filter(j => /^[a-zA-Z]/.test(j));
  const jobs = enJournals.map(journal => ({
    journal,
    retmax: (isNcsCoreJournal(journal) || isBoneCoreJournal(journal)) ? BONE_RETMAX : NORMAL_RETMAX
  }));

  updateProgress(0, jobs.length, "准备检索...");

  await mapWithConcurrency(
    jobs,
    SEARCH_CONCURRENCY,
    async job => searchPubMed(job.journal, fmt(dateFrom), fmt(dateTo), job.retmax),
    (done, total, job, result) => {
      if (Array.isArray(result)) {
        articles.push(...result);
      } else if (result?.__error) {
        console.error(`Error searching ${job.journal}:`, result.__error);
        showToast(`检索 ${job.journal} 失败: ${result.__error.message}`, "error");
      }
      updateProgress(done, total, `已完成 ${done}/${total} 个期刊`);
      updateStats();
      renderResults();
    }
  );

  articles = dedupeArticles(articles)
    .sort((a, b) => articleTimestamp(b) - articleTimestamp(a))
    .slice(0, HARD_CANDIDATE_LIMIT)
    .map(a => ({
      ...a,
      relevance: a.relevance ?? 50,
      aimFit: a.aimFit ?? 50,
      novelty: a.novelty ?? 50,
      routineRisk: a.routineRisk ?? 50,
      translationalValue: a.translationalValue ?? 50,
      reasonShort: a.reasonShort || "",
      tags: Array.isArray(a.tags) ? a.tags : [],
      riskTags: Array.isArray(a.riskTags) ? a.riskTags : [],
      preScore: a.preScore ?? 50,
      tasteBoost: a.tasteBoost ?? 50,
      starRating: a.starRating ?? 0,
      ncsBoost: a.ncsBoost ?? (isNcsCoreJournal(a.journal) ? 4 : 0)
    }));

  if (STRICT_MEDICAL_ONLY) {
    const beforeMedicalFilter = articles.length;
    articles = articles.filter(hasMedicalSignal);
    const removed = beforeMedicalFilter - articles.length;
    if (removed > 0) {
      showToast(`Medical-only filter removed ${removed} non-medical candidates.`, "info");
    }
  }

  recomputeScoresAndSort();
  updateStats();
  renderResults();
  showCnJournalLinks(days);

  if (s.apiKey && articles.length > 0) {
    if (s.twoStageAnalysis) {
      document.getElementById("searchInfo").textContent = "正在进行轻量预分析...";
      for (let i = 0; i < articles.length; i++) {
        if (searchAborted) break;
        const a = articles[i];
        if (a.abstract === "No abstract available") {
          a.reasonShort = "无摘要，保留候选";
          a.preScore = computePreScore(a);
          continue;
        }
        updateProgress(i, articles.length, `预分析: ${a.title.substring(0, 36)}...`);
        try {
          const pre = await preAnalyzeArticle(a);
          a.relevance = pre.relevance;
          a.aimFit = pre.aimFit;
          a.novelty = pre.novelty;
          a.routineRisk = pre.routineRisk;
          a.translationalValue = pre.translationalValue;
          a.reasonShort = pre.reasonShort;
          a.tags = pre.tags;
          a.preScore = computePreScore(a);
        } catch (err) {
          console.error("pre-analysis error:", err);
          a.reasonShort = "预分析失败，保留候选";
          a.preScore = computePreScore(a);
        }
        if ((i + 1) % 6 === 0) {
          recomputeScoresAndSort();
          updateStats();
          renderResults();
        }
        await sleep(220);
      }
      recomputeScoresAndSort();
      updateStats();
      renderResults();
      const deepTargets = articles.filter(a => a.abstract !== "No abstract available").slice(0, cap);
      document.getElementById("searchInfo").textContent = `正在深度分析 Top ${deepTargets.length}...`;
      await runDeepAnalysis(deepTargets);
    } else {
      document.getElementById("searchInfo").textContent = "正在进行全量深度分析...";
      await runDeepAnalysis(articles.filter(a => a.abstract !== "No abstract available"));
    }
  } else if (!s.apiKey) {
    showToast("未配置 API Key，跳过 AI 分析", "info");
  }

  document.getElementById("searchBtn").style.display = "inline-flex";
  document.getElementById("stopBtn").style.display = "none";
  document.getElementById("searchProgress").style.display = "none";

  if (articles.length > 0) {
    document.getElementById("searchInfo").textContent = `检索完成：共 ${articles.length} 篇候选，深度分析 ${analyzedCount} 篇，默认展示前 ${cap} 篇`;
    showToast(`检索完成，共找到 ${articles.length} 篇文献`, "success");
  } else {
    document.getElementById("searchInfo").textContent = "未检索到文献";
    showToast("该时间段内未检索到文献，尝试扩大时间范围", "info");
  }

  updateStats();
  renderResults();
}

function stopSearch() {
  searchAborted = true;
  showToast("正在停止检索...", "info");
}

function updateProgress(current, total, text) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  document.getElementById("progressFill").style.width = `${pct}%`;
  document.getElementById("progressText").textContent = text;
}

function updateStats() {
  document.getElementById("statTotal").textContent = articles.length;
  document.getElementById("statJournals").textContent = new Set(articles.map(a => a.journal)).size;
  document.getElementById("statAnalyzed").textContent = analyzedCount;
  document.getElementById("statTerms").textContent = Object.keys(glossaryTerms).length;
}

function showCnJournalLinks() {
  const section = document.getElementById("cnJournalSection");
  const container = document.getElementById("cnJournalLinks");
  section.style.display = "block";
  container.innerHTML = "";
  CN_JOURNALS.forEach(j => {
    const card = document.createElement("div");
    card.className = "cn-link-card";
    card.innerHTML = `<span class="name">${escapeHtml(j.name)}</span><span><a href="${j.cnki}" target="_blank">CNKI</a>&nbsp;|&nbsp;<a href="${j.wanfang}" target="_blank">万方</a></span>`;
    container.appendChild(card);
  });
}

function toggleShowCandidates() {
  showAllCandidates = !showAllCandidates;
  renderResults();
}

function getVisibleArticles() {
  const s = getSettings();
  const cap = clamp(parseInt(s.candidateCap, 10) || DEFAULT_CANDIDATE_CAP, 5, 100);
  const filtered = currentFilter === "all" ? articles : articles.filter(a => a.journal === currentFilter);
  if (showAllCandidates) return { filtered, visible: filtered, hidden: 0, cap };
  return { filtered, visible: filtered.slice(0, cap), hidden: Math.max(0, filtered.length - cap), cap };
}

function renderResults() {
  const area = document.getElementById("resultsArea");
  if (articles.length === 0) {
    const searching = document.getElementById("searchProgress").style.display !== "none";
    area.innerHTML = searching
      ? '<div class="loading"><div class="spinner"></div><p>正在检索中...</p></div>'
      : '<div class="empty-state"><div class="icon">📚</div><h3>暂无结果</h3><p style="margin-top:8px">点击“开始检索”获取最新口腔医学文献</p></div>';
    renderJournalFilter();
    return;
  }

  renderJournalFilter();
  const { filtered, visible, hidden, cap } = getVisibleArticles();
  const grouped = {};
  visible.forEach(a => {
    if (!grouped[a.journal]) grouped[a.journal] = [];
    grouped[a.journal].push(a);
  });

  let html = "";
  if (filtered.length > cap) {
    html += `<div class="result-limit-note"><span>当前筛选共 ${filtered.length} 篇，默认展示前 ${cap} 篇高分候选。</span><button class="btn btn-outline" onclick="toggleShowCandidates()">${showAllCandidates ? "收起到 Top 列表" : "查看全部候选"}</button></div>`;
  }
  if (visible.length === 0) {
    html += '<div class="empty-state"><p>当前筛选无结果</p></div>';
  } else {
    Object.keys(grouped).forEach(journal => {
      const list = grouped[journal];
      html += `<div class="articles-section"><h2>${escapeHtml(journal)} (${list.length})</h2>`;
      list.forEach(a => {
        const globalIdx = articles.indexOf(a);
        html += renderArticleCard(a, globalIdx);
      });
      html += "</div>";
    });
  }
  if (hidden > 0 && !showAllCandidates) {
    html += `<div class="result-limit-note"><span>还有 ${hidden} 篇候选未展示。</span><button class="btn btn-outline" onclick="toggleShowCandidates()">查看全部候选</button></div>`;
  }
  area.innerHTML = html;
}

function renderStarButtons(a, idx) {
  return [1, 2, 3, 4, 5].map(n => `<button class="star-btn ${a.starRating >= n ? "active" : ""}" onclick="rateArticle(${idx}, ${n})">${n}★</button>`).join("");
}

function renderArticleCard(a, idx) {
  const authorsStr = a.authors.length > 3 ? `${a.authors.slice(0, 3).join(", ")} et al.` : a.authors.join(", ");
  const doiLink = a.doi ? `<a href="https://doi.org/${a.doi}" target="_blank" style="color:var(--primary);text-decoration:none">DOI</a>` : "";
  const pmidLink = a.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/" target="_blank" style="color:var(--primary);text-decoration:none">PubMed</a>` : "";
  const riskTagsHtml = (a.riskTags || []).map(tag => `<span class="risk-tag high">${escapeHtml(tag)}</span>`).join("");
  const aiTagsHtml = (a.tags || []).slice(0, 4).map(tag => `<span class="risk-tag">${escapeHtml(tag)}</span>`).join("");

  return `
    <div class="article-card">
      <div class="article-title">${escapeHtml(a.title)}</div>
      ${a.titleCn ? `<div class="article-title-cn">${escapeHtml(a.titleCn)}</div>` : ""}
      <div class="article-meta">
        <span>&#128100; ${escapeHtml(authorsStr)}</span>
        <span>&#128197; ${escapeHtml(a.pubDate)}</span>
        <span>&#128214; ${escapeHtml(a.journal)}</span>
        ${doiLink ? `<span>${doiLink}</span>` : ""}
        ${pmidLink ? `<span>${pmidLink}</span>` : ""}
      </div>
      <div class="pre-analysis">
        <div class="score-line">
          <span class="score-main">预分析分: ${Number(a.preScore || 0).toFixed(1)}</span>
          <span>相关度: ${Math.round(a.relevance || 0)}</span>
          <span>Aim匹配: ${Math.round(a.aimFit || 0)}</span>
          <span>新颖性: ${Math.round(a.novelty || 0)}</span>
          <span>Taste加成: ${Math.round(a.tasteBoost || 0)}</span>
          ${a.ncsBoost ? `<span>NCS+${a.ncsBoost}</span>` : ""}
        </div>
        ${(riskTagsHtml || aiTagsHtml) ? `<div class="risk-tags">${riskTagsHtml}${aiTagsHtml}</div>` : ""}
        ${a.reasonShort ? `<div class="reason">${escapeHtml(a.reasonShort)}</div>` : ""}
        <div class="star-row">
          <span class="star-label">你的评分:</span>
          ${renderStarButtons(a, idx)}
        </div>
      </div>
      ${a.keywords.length > 0 ? `<div class="article-keywords">${a.keywords.map(k => `<span class="keyword-tag">${escapeHtml(k)}</span>`).join("")}</div>` : ""}
      <div class="article-abstract collapsed" id="abstract-${idx}">${escapeHtml(a.abstract)}</div>
      <div class="article-actions">
        <button class="expand-btn" onclick="toggleAbstract(${idx})">展开摘要</button>
        ${a.analyzed ? `<button class="expand-btn" onclick="toggleAnalysis(${idx})">查看AI分析</button>` : ""}
        ${!a.analyzed && a.abstract !== "No abstract available" ? `<button class="expand-btn" onclick="analyzeOne(${idx})">AI分析此文</button>` : ""}
      </div>
      ${a.analyzed ? `<div class="ai-analysis" id="analysis-${idx}"><h4>&#129302; AI分析</h4><div class="method-summary">${escapeHtml(a.methodSummary)}</div>${a.glossary.length > 0 ? `<table class="glossary-table"><thead><tr><th>英文术语</th><th>中文翻译</th></tr></thead><tbody>${a.glossary.map(g => `<tr><td>${escapeHtml(g.en)}</td><td>${escapeHtml(g.cn)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : ""}
    </div>`;
}

function renderJournalFilter() {
  const filterDiv = document.getElementById("journalFilter");
  const tagsDiv = document.getElementById("journalTags");
  if (articles.length === 0) {
    filterDiv.style.display = "none";
    return;
  }
  filterDiv.style.display = "block";
  const counts = {};
  articles.forEach(a => { counts[a.journal] = (counts[a.journal] || 0) + 1; });
  let html = `<span class="journal-tag ${currentFilter === "all" ? "active" : ""}" onclick="setFilter('all')">全部<span class="count">(${articles.length})</span></span>`;
  Object.keys(counts).sort().forEach(j => {
    const encoded = encodeURIComponent(j);
    html += `<span class="journal-tag ${currentFilter === j ? "active" : ""}" onclick="setFilterByEncoded('${encoded}')">${escapeHtml(j)}<span class="count">(${counts[j]})</span></span>`;
  });
  tagsDiv.innerHTML = html;
}

function setFilter(journal) {
  currentFilter = journal;
  showAllCandidates = false;
  renderResults();
}

function setFilterByEncoded(encodedJournal) {
  setFilter(decodeURIComponent(encodedJournal));
}

async function analyzeOne(idx) {
  const s = getSettings();
  if (!s.apiKey) {
    showToast("请先配置 API Key", "error");
    return;
  }
  const a = articles[idx];
  if (!a) return;
  showToast("正在分析...", "info");
  try {
    const analysis = await analyzeArticle(a);
    a.titleCn = analysis.titleCn || "";
    a.methodSummary = analysis.methodSummary || "";
    a.glossary = analysis.glossary || [];
    if (!a.analyzed) analyzedCount += 1;
    a.analyzed = true;
    (a.glossary || []).forEach(term => {
      if (term.en && term.cn) glossaryTerms[term.en.toLowerCase()] = { en: term.en, cn: term.cn, source: a.journal };
    });
    updateStats();
    renderResults();
    showToast("分析完成", "success");
  } catch (err) {
    showToast(`分析失败: ${err.message}`, "error");
  }
}

function exportMarkdown() {
  if (articles.length === 0) {
    showToast("暂无文献数据可导出", "error");
    return;
  }

  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const days = document.getElementById("timePeriod").value;
  const periodName = { "1": "日报", "3": "三日报", "7": "周报", "30": "月报" }[days] || "报告";

  let md = `# 口腔医学文献${periodName}\n\n`;
  md += `> 生成日期：${dateStr} | 检索范围：过去${days}天 | 共${articles.length}篇候选\n\n`;
  md += "---\n\n";

  const grouped = {};
  articles.forEach(a => {
    if (!grouped[a.journal]) grouped[a.journal] = [];
    grouped[a.journal].push(a);
  });

  Object.keys(grouped).sort().forEach(journal => {
    md += `## ${journal}\n\n`;
    grouped[journal].forEach((a, i) => {
      md += `### ${i + 1}. ${a.title}\n\n`;
      if (a.titleCn) md += `- **中文标题**: ${a.titleCn}\n`;
      md += `- **作者**: ${(a.authors || []).join(", ")}\n`;
      md += `- **期刊**: ${a.journal}\n`;
      md += `- **发表日期**: ${a.pubDate}\n`;
      md += `- **预分析分**: ${a.preScore}\n`;
      if (a.starRating) md += `- **我的评分**: ${a.starRating} 星\n`;
      if ((a.riskTags || []).length > 0) md += `- **风险标签**: ${(a.riskTags || []).join(" / ")}\n`;
      if (a.doi) md += `- **DOI**: [${a.doi}](https://doi.org/${a.doi})\n`;
      if (a.pmid) md += `- **PubMed**: [${a.pmid}](https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/)\n`;
      if ((a.keywords || []).length > 0) md += `- **关键词**: ${a.keywords.join(", ")}\n`;
      if (a.reasonShort) md += `- **预分析说明**: ${a.reasonShort}\n`;
      md += `\n**摘要**:\n\n${a.abstract}\n\n`;
      if (a.methodSummary) md += `**方法与结论摘要**:\n\n${a.methodSummary}\n\n`;
      if ((a.glossary || []).length > 0) {
        md += "**术语**:\n\n";
        md += "| 英文 | 中文 |\n|------|------|\n";
        a.glossary.forEach(g => { md += `| ${g.en} | ${g.cn} |\n`; });
        md += "\n";
      }
      md += "---\n\n";
    });
  });

  const terms = Object.values(glossaryTerms).sort((a, b) => a.en.localeCompare(b.en));
  if (terms.length > 0) {
    md += "## 专业术语中英对照表\n\n";
    md += "| 英文 | 中文 | 来源 |\n|------|------|------|\n";
    terms.forEach(t => { md += `| ${t.en} | ${t.cn} | ${t.source} |\n`; });
    md += "\n";
  }

  md += "## 中文期刊\n\n以下中文期刊请通过 CNKI 或万方数据库手动查阅：\n\n";
  CN_JOURNALS.forEach(j => {
    md += `- **${j.name}**: [CNKI](${j.cnki}) | [万方](${j.wanfang})\n`;
  });

  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `口腔文献${periodName}_${dateStr}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast("报告已下载", "success");
}

// Override with resilient search flow
async function startSearch() {
  const s = getSettings();
  const journals = withNcsJournals(s.journals || DEFAULT_JOURNALS, s.enableNcsCore);
  const days = parseInt(document.getElementById("timePeriod").value, 10);
  const cap = clamp(parseInt(s.candidateCap, 10) || DEFAULT_CANDIDATE_CAP, 5, 100);
  const dateTo = new Date();
  const dateFrom = new Date();
  dateFrom.setDate(dateTo.getDate() - days);
  const fmt = d => `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;

  articles = [];
  glossaryTerms = {};
  analyzedCount = 0;
  searchAborted = false;
  currentFilter = "all";
  showAllCandidates = false;
  nextEutilsAllowedAt = 0;

  document.getElementById("searchBtn").style.display = "none";
  document.getElementById("stopBtn").style.display = "inline-flex";
  document.getElementById("searchProgress").style.display = "block";
  document.getElementById("statsSection").style.display = "flex";
  document.getElementById("searchInfo").textContent = "Searching...";

  const enJournals = journals.filter(j => /^[a-zA-Z]/.test(j));
  const jobs = enJournals.map(journal => ({
    journal,
    retmax: (isNcsCoreJournal(journal) || isBoneCoreJournal(journal)) ? BONE_RETMAX : NORMAL_RETMAX
  }));
  const effectiveConcurrency = jobs.length > 18 ? 1 : SEARCH_CONCURRENCY;

  let fetchFailCount = 0;
  let fetchFailToastCount = 0;
  updateProgress(0, jobs.length, "Preparing fetch...");

  await mapWithConcurrency(
    jobs,
    effectiveConcurrency,
    async job => searchPubMed(job.journal, fmt(dateFrom), fmt(dateTo), job.retmax),
    (done, total, job, result) => {
      if (Array.isArray(result)) {
        articles.push(...result);
      } else if (result?.__error) {
        fetchFailCount += 1;
        console.error(`Error searching ${job.journal}:`, result.__error);
        if (fetchFailToastCount < 3) {
          showToast(`Search failed for ${job.journal}: ${result.__error.message}`, "error");
          fetchFailToastCount += 1;
        }
      }
      updateProgress(done, total, `Completed ${done}/${total} journals`);
      updateStats();
      renderResults();
    }
  );

  if (fetchFailCount > 3) {
    showToast(`${fetchFailCount} journals failed (with retries).`, "info");
  }

  articles = dedupeArticles(articles)
    .sort((a, b) => articleTimestamp(b) - articleTimestamp(a))
    .slice(0, HARD_CANDIDATE_LIMIT)
    .map(a => ({
      ...a,
      relevance: a.relevance ?? 50,
      aimFit: a.aimFit ?? 50,
      novelty: a.novelty ?? 50,
      routineRisk: a.routineRisk ?? 50,
      translationalValue: a.translationalValue ?? 50,
      reasonShort: a.reasonShort || "",
      tags: Array.isArray(a.tags) ? a.tags : [],
      riskTags: Array.isArray(a.riskTags) ? a.riskTags : [],
      preScore: a.preScore ?? 50,
      tasteBoost: a.tasteBoost ?? 50,
      starRating: a.starRating ?? 0,
      ncsBoost: a.ncsBoost ?? (isNcsCoreJournal(a.journal) ? 4 : 0)
    }));

  recomputeScoresAndSort();
  updateStats();
  renderResults();
  showCnJournalLinks(days);

  if (s.apiKey && articles.length > 0) {
    if (s.twoStageAnalysis) {
      document.getElementById("searchInfo").textContent = "Running pre-analysis...";
      for (let i = 0; i < articles.length; i++) {
        if (searchAborted) break;
        const a = articles[i];
        if (a.abstract === "No abstract available") {
          a.reasonShort = "No abstract, kept as candidate";
          a.preScore = computePreScore(a);
          continue;
        }
        updateProgress(i, articles.length, `Pre-analysis: ${a.title.substring(0, 36)}...`);
        try {
          const pre = await preAnalyzeArticle(a);
          a.relevance = pre.relevance;
          a.aimFit = pre.aimFit;
          a.novelty = pre.novelty;
          a.routineRisk = pre.routineRisk;
          a.translationalValue = pre.translationalValue;
          a.reasonShort = pre.reasonShort;
          a.tags = pre.tags;
          a.preScore = computePreScore(a);
        } catch (err) {
          console.error("pre-analysis error:", err);
          a.reasonShort = "Pre-analysis failed, kept as candidate";
          a.preScore = computePreScore(a);
        }
        if ((i + 1) % 6 === 0) {
          recomputeScoresAndSort();
          updateStats();
          renderResults();
        }
        await sleep(220);
      }

      if (STRICT_MEDICAL_ONLY) {
        const beforeAiMedicalFilter = articles.length;
        articles = articles.filter(a => (hasMedicalSignal(a) || Number(a.relevance || 0) >= 45 || Number(a.translationalValue || 0) >= 45));
        const removedByAi = beforeAiMedicalFilter - articles.length;
        if (removedByAi > 0) {
          showToast(`AI medical filter removed ${removedByAi} items.`, "info");
        }
      }

      recomputeScoresAndSort();
      updateStats();
      renderResults();

      const deepTargets = articles.filter(a => a.abstract !== "No abstract available").slice(0, cap);
      document.getElementById("searchInfo").textContent = `Running deep-analysis Top ${deepTargets.length}...`;
      await runDeepAnalysis(deepTargets);
    } else {
      document.getElementById("searchInfo").textContent = "Running deep-analysis for all...";
      await runDeepAnalysis(articles.filter(a => a.abstract !== "No abstract available"));
    }
  } else if (!s.apiKey) {
    showToast("API Key not configured, skipped AI analysis", "info");
  }

  document.getElementById("searchBtn").style.display = "inline-flex";
  document.getElementById("stopBtn").style.display = "none";
  document.getElementById("searchProgress").style.display = "none";

  if (articles.length > 0) {
    document.getElementById("searchInfo").textContent = `Done: ${articles.length} candidates, ${analyzedCount} deep-analyzed, showing Top ${cap}`;
    showToast(`Search done: ${articles.length} papers`, "success");
  } else {
    document.getElementById("searchInfo").textContent = "No papers found";
    showToast("No papers in this range; try a wider time range", "info");
  }

  updateStats();
  renderResults();
}

// ============ Init ============
tasteProfile = createDefaultTasteProfile();
loadTasteProfile();
loadSettings();
refreshTasteEditor();
const ncsToggle = document.getElementById("enableNcsCore");
if (ncsToggle) ncsToggle.addEventListener("change", handleNcsToggle);
</script>
</body>
</html>
