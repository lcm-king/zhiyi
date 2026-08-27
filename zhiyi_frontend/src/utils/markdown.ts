/**
 * 轻量级 Markdown 渲染器（无第三方依赖）
 * 安全策略：先转义全部 HTML 实体，再仅生成白名单标签，避免 XSS。
 * 支持：标题 / 粗体 / 斜体 / 行内代码 / 代码块 / 有序&无序列表 / 引用 / 分隔线 / 表格 / 链接 / 段落换行
 */

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function inline(text: string): string {
  let t = text
  // 行内代码
  t = t.replace(/`([^`]+)`/g, (_m, code: string) => `<code>${code}</code>`)
  // 链接（仅允许 http/https）
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label: string, url: string) =>
    `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
  )
  // 粗体
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // 斜体
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  t = t.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>')
  return t
}

export function renderMarkdown(src?: string | null): string {
  if (!src) return ''
  const lines = escapeHtml(String(src).replace(/\r\n/g, '\n')).split('\n')
  const out: string[] = []
  let i = 0
  let para: string[] = []
  let listTag: 'ul' | 'ol' | null = null
  let quote: string[] = []
  let inFence = false
  let fenceLang = ''
  let fence: string[] = []

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.map((l) => inline(l)).join('<br>')}</p>`)
      para = []
    }
  }
  const flushQuote = () => {
    if (quote.length) {
      out.push(`<blockquote>${quote.map((l) => `<p>${inline(l)}</p>`).join('')}</blockquote>`)
      quote = []
    }
  }
  const flushList = () => {
    if (listTag) {
      out.push(`</${listTag}>`)
      listTag = null
    }
  }
  const closeBlocks = () => {
    flushList()
    flushQuote()
    flushPara()
  }
  const splitCells = (row: string) =>
    row.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())

  while (i < lines.length) {
    const line = lines[i]

    // 围栏代码块
    const fenceMatch = line.match(/^```([\w+-]*)\s*$/)
    if (fenceMatch) {
      if (!inFence) {
        closeBlocks()
        inFence = true
        fenceLang = fenceMatch[1] || ''
        fence = []
      } else {
        out.push(`<pre><code${fenceLang ? ` class="language-${fenceLang}"` : ''}>${fence.join('\n')}</code></pre>`)
        inFence = false
        fenceLang = ''
        fence = []
      }
      i++
      continue
    }
    if (inFence) {
      fence.push(line)
      i++
      continue
    }

    // 空行
    if (!line.trim()) {
      closeBlocks()
      i++
      continue
    }

    // 标题
    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      closeBlocks()
      const level = heading[1].length
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      i++
      continue
    }

    // 分隔线
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      closeBlocks()
      out.push('<hr>')
      i++
      continue
    }

    // 表格（表头行 + 分隔行）
    if (
      i + 1 < lines.length &&
      line.includes('|') &&
      /-/.test(lines[i + 1]) &&
      /^\|?[\s:|-]+\|?$/.test(lines[i + 1])
    ) {
      closeBlocks()
      const head = splitCells(line).map(inline)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(splitCells(lines[i]).map(inline))
        i++
      }
      out.push(
        `<div class="md-table-wrap"><table><thead><tr>${head
          .map((c) => `<th>${c}</th>`)
          .join('')}</tr></thead>` +
          `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
      )
      continue
    }

    // 引用
    const bq = line.match(/^>\s?(.*)$/)
    if (bq) {
      flushList()
      flushPara()
      quote.push(bq[1])
      i++
      continue
    }

    // 无序列表
    const ul = line.match(/^[-*+]\s+(.*)$/)
    if (ul) {
      flushQuote()
      flushPara()
      if (listTag !== 'ul') {
        flushList()
        out.push('<ul>')
        listTag = 'ul'
      }
      out.push(`<li>${inline(ul[1])}</li>`)
      i++
      continue
    }

    // 有序列表
    const ol = line.match(/^\d+[.)]\s+(.*)$/)
    if (ol) {
      flushQuote()
      flushPara()
      if (listTag !== 'ol') {
        flushList()
        out.push('<ol>')
        listTag = 'ol'
      }
      out.push(`<li>${inline(ol[1])}</li>`)
      i++
      continue
    }

    // 普通段落行
    flushList()
    flushQuote()
    para.push(line)
    i++
  }

  if (inFence) {
    out.push(`<pre><code${fenceLang ? ` class="language-${fenceLang}"` : ''}>${fence.join('\n')}</code></pre>`)
  }
  closeBlocks()
  return out.join('\n')
}
