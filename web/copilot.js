'use strict';
// All model text is escaped before the small supported Markdown subset is rendered.
function copilotInline(value){
  let text=esc(value);
  text=text.replace(/`([^`\n]+)`/g,(_,v)=>{const label=phases[v]||({observed_products:'Số liệu thực tế','plan.prepared':'Sản lượng đề xuất'}[v]);return '<code>'+(label?esc(label):v)+'</code>'});
  return text.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>');
}
function copilotSections(answer){
  const sections=[];
  let section=null;
  const start=title=>{section={title:title.replace(/[:：]\s*$/,'').trim(),lines:[]};sections.push(section)};
  for(const original of String(answer||'').split(/\r?\n/)){
    const line=original.trim();
    if(!line){if(section)section.lines.push('');continue}
    if(/^[-*_]{3,}$/.test(line))continue;
    const heading=line.match(/^#{1,4}\s+(.+)$/);
    const labelled=line.match(/^(?:[-*•]\s+|\d+[.)]\s+)?\*\*([^*]+)\*\*\s*(.*)$/);
    if(heading){start(heading[1]);continue}
    if(labelled && (/[：:]$/.test(labelled[1]) || /^[：:]/.test(labelled[2]) || !labelled[2]&&!/^\d/.test(labelled[1]))){start(labelled[1]);const body=labelled[2].replace(/^[：:]\s*/,'');if(body)section.lines.push(body);continue}
    if(!section)start('Tổng quan');
    section.lines.push(line);
  }
  return sections;
}
function copilotSectionStyle(title){
  const t=title.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/đ/g,'d');
  if(/xac nhan|phe duyet|buoc|tiep theo|hanh dong/.test(t))return {icon:'check',tone:'action'};
  if(/luu y|canh bao|han che|thieu du lieu/.test(t))return {icon:'shield',tone:'caution'};
  if(/cach tinh|tinh toan|cong thuc/.test(t))return {icon:'activity',tone:'calculation'};
  if(/nhu cau|du bao/.test(t))return {icon:'chart',tone:'forecast'};
  if(/san luong|san xuat|de xuat/.test(t))return {icon:'bread',tone:'recommendation'};
  if(/gia|giam gia/.test(t))return {icon:'tag',tone:'recommendation'};
  return {icon:'info',tone:'reason'};
}
function copilotBody(lines){
  let html='',paragraph=[],items=[];
  const flushParagraph=()=>{if(paragraph.length){html+='<p>'+paragraph.map(copilotInline).join('<br>')+'</p>';paragraph=[]}};
  const flushItems=()=>{if(items.length){html+='<ul>'+items.map(s=>'<li>'+copilotInline(s)+'</li>').join('')+'</ul>';items=[]}};
  for(const line of lines){
    const bullet=line.match(/^(?:[-*•]\s+|\d+[.)]\s+)(.+)$/);
    if(!line){flushParagraph();flushItems();continue}
    if(bullet){flushParagraph();items.push(bullet[1])}else{flushItems();paragraph.push(line)}
  }
  flushParagraph();flushItems();return html;
}
function copilotChatMessage(message){
  if(message.user)return '<div class="chat-message user-message">'+esc(message.text)+'</div>';
  if(message.error)return '<div class="copilot-error">'+icon('info')+'<p>'+esc(message.text)+'</p></div>';
  return copilotResponse(message.result||{answer:message.text},true);
}
function copilotPrompt(question){
  const format='\n\nYêu cầu trình bày: chia câu trả lời thành 2–4 mục ngắn có tiêu đề in đậm và dấu hai chấm: Đề xuất, Lý do, Cách tính (nếu có số liệu), Bước tiếp theo (nếu cần xác nhận). Mỗi mục 1–2 câu; tránh đoạn dài và không cần emoji.';
  return question.length+format.length<=4000?question+format:question;
}
function copilotResponse(result, compact=false){
  const sections=copilotSections(result.answer);
  return '<div class="copilot-response '+(compact?'copilot-compact':'')+'"><div class="copilot-response-heading"><span class="copilot-avatar">'+icon('spark')+'</span><div><strong>SmartFresh Copilot</strong><span>Phân tích ca · Giải thích từ dữ liệu</span></div></div><div class="copilot-sections">'+sections.map(s=>{const style=copilotSectionStyle(s.title);return '<section class="copilot-section '+style.tone+'"><div class="copilot-section-icon">'+icon(style.icon)+'</div><div class="copilot-section-content"><h3>'+copilotInline(s.title)+'</h3>'+copilotBody(s.lines)+'</div></section>'}).join('')+'</div>'+(result.model?'<details class="copilot-technical"><summary>Chi tiết phản hồi</summary><dl><dt>Model</dt><dd>'+esc(result.model)+'</dd>'+(result.response_id?'<dt>Mã phản hồi</dt><dd>'+esc(result.response_id)+'</dd>':'')+(result.tools_used?'<dt>Công cụ đọc dữ liệu</dt><dd>'+esc(result.tools_used.join(', '))+'</dd>':'')+'</dl></details>':'')+'</div>';
}
