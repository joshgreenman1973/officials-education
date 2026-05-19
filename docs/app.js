(async function(){
  const $ = s => document.querySelector(s);
  const $$ = s => document.querySelectorAll(s);
  let officials = [], schoolSector = {};
  try {
    const [o, sc] = await Promise.all([fetch("data/officials.json"), fetch("data/schools.json")]);
    officials = await o.json();
    (await sc.json()).forEach(s => { schoolSector[s.school] = s.sector; });
  } catch(e){
    $("#tbody").innerHTML = `<tr><td colspan="8" class="empty">Failed to load data: ${e.message}</td></tr>`;
    return;
  }
  const DEGREE_RANK = {None:0,Bachelor:1,BA:1,BS:1,BBA:1,BEng:1,BFA:1,BSW:1,LLB:1,Master:2,MA:2,MS:2,MBA:2,MPA:2,MPP:2,MPH:2,MEd:2,MFA:2,MDiv:2,LLM:2,MSW:2,JD:3,MD:3,DO:3,PhD:4,EdD:4,DDS:4,DVM:4};
  const isGrad = d => DEGREE_RANK[d] >= 2;
  const isUg = d => !d || DEGREE_RANK[d] === 1;
  officials.forEach(o => {
    o.education = o.education || [];
    o._undergrad = o.education.filter(e => isUg(e.degree));
    o._grad = o.education.filter(e => isGrad(e.degree));
    o._ug_school = o._undergrad[0]?.school || o.education[0]?.school || "";
    o._ug_field = o._undergrad.map(e=>e.field).filter(Boolean).join(", ") || o.education.map(e=>e.field).filter(Boolean).join(", ") || "";
    const sectors = new Set(o.education.map(e => schoolSector[e.school] || "unknown"));
    o._sectors = sectors;
    if (sectors.size === 0) o._sector_summary = "none";
    else if (sectors.has("public") && sectors.has("private")) o._sector_summary = "mixed";
    else if (sectors.size === 1) o._sector_summary = [...sectors][0];
    else o._sector_summary = [...sectors].filter(s=>s!=="unknown")[0] || "unknown";
    let hi = "None", r = 0;
    o.education.forEach(e => { const x = DEGREE_RANK[e.degree]||0; if (x>r){r=x;hi=e.degree;} });
    o._highest = hi;
    o._highest_bucket = r===0?"None":r===1?"Bachelor":r===2?"Master":(hi==="JD"?"JD":hi==="MD"?"MD":"PhD");
  });
  const fill = (sel, arr) => { const el = $(sel); arr.forEach(v => { const op = document.createElement("option"); op.value=v; op.textContent=v; el.appendChild(op); }); };
  fill("#f-office", [...new Set(officials.map(o=>o.office))].sort());
  fill("#f-state", [...new Set(officials.map(o=>o.state).filter(Boolean))].sort());
  fill("#f-party", [...new Set(officials.map(o=>o.party).filter(Boolean))].sort());
  function renderStats(rows){
    const total = rows.length;
    const pub = rows.filter(o=>o._sector_summary==="public").length;
    const priv = rows.filter(o=>o._sector_summary==="private").length;
    const grad = rows.filter(o=>o._grad.length).length;
    $("#stats").innerHTML = `
      <div class="stat"><div class="n">${total}</div><div class="l">Officials shown</div></div>
      <div class="stat"><div class="n">${pub}</div><div class="l">Public-school only</div></div>
      <div class="stat"><div class="n">${priv}</div><div class="l">Private-school only</div></div>
      <div class="stat"><div class="n">${grad}</div><div class="l">Hold a graduate degree</div></div>`;
  }
  let sortKey="name", sortDir=1;
  function fstate(){
    return {q:$("#q").value.trim().toLowerCase(),office:$("#f-office").value,state:$("#f-state").value,party:$("#f-party").value,sector:$("#f-sector").value,degree:$("#f-degree").value};
  }
  function escape(s){return String(s||"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function sortVal(o,k){
    switch(k){
      case "name": return o.name.split(" ").slice(-1)[0].toLowerCase();
      case "office": return ({Senator:1,Representative:2,Governor:3,Mayor:4}[o.office]||9)+" "+(o.district||o.state||"");
      case "state": return (o.state||"")+(o.district||"");
      case "party": return o.party||"";
      case "undergrad": return (o._ug_school||"").toLowerCase();
      case "major": return (o._ug_field||"").toLowerCase();
      case "grad": return o._grad.length?(o._grad[0].school||"").toLowerCase():"zzz";
      case "sector": return o._sector_summary||"";
    } return "";
  }
  function apply(){
    const f = fstate();
    let rows = officials.filter(o => {
      if (f.office && o.office !== f.office) return false;
      if (f.state && o.state !== f.state) return false;
      if (f.party && o.party !== f.party) return false;
      if (f.sector){
        if (f.sector === "mixed"){ if (o._sector_summary !== "mixed") return false; }
        else if (!o._sectors.has(f.sector)) return false;
      }
      if (f.degree && o._highest_bucket !== f.degree) return false;
      if (f.q){
        const hay = [o.name,o.state,o.city||"",o.district||"",o._ug_school,o._ug_field,
          ...o.education.map(e=>`${e.school||""} ${e.degree||""} ${e.field||""}`)].join(" ").toLowerCase();
        if (!hay.includes(f.q)) return false;
      }
      return true;
    });
    rows.sort((a,b)=>{let va=sortVal(a,sortKey),vb=sortVal(b,sortKey);if(va==null)va="";if(vb==null)vb="";return va<vb?-1*sortDir:va>vb?1*sortDir:0;});
    renderStats(rows);
    const body = $("#tbody");
    if (!rows.length){ body.innerHTML=""; $("#empty").style.display="block"; return; }
    $("#empty").style.display="none";
    body.innerHTML = rows.map(o => {
      const partyTag = o.party ? `<span class="tag ${o.party}">${o.party}</span>` : "";
      const stateLabel = o.office==="Mayor" && o.city ? o.city : o.state;
      const officeLabel = o.office==="Representative" ? `Rep. ${o.district||""}` : o.office;
      const ug = o._undergrad.length
        ? o._undergrad.map(e=>`<div class="row">${escape(e.school)}${e.degree?` <span class="deg">(${e.degree})</span>`:""}</div>`).join("")
        : (o.education.length ? `<div class="row">${escape(o.education[0].school||"")}</div>` : `<span class="deg">Not listed</span>`);
      const grad = o._grad.length
        ? o._grad.map(e=>`<div class="row">${escape(e.school)} <span class="deg">(${e.degree||""}${e.field?", "+escape(e.field):""})</span></div>`).join("")
        : `<span class="deg">—</span>`;
      const sec = o._sector_summary;
      const sectorClass = sec==="mixed"?"":(sec||"unknown");
      const sectorLabel = sec==="none"?"—":sec==="mixed"?"Public + Private":(sec||"unknown");
      return `<tr>
        <td class="name"><a href="${o.wikipedia_url||"#"}" target="_blank" rel="noopener">${escape(o.name)}</a></td>
        <td>${escape(officeLabel)}</td><td>${escape(stateLabel)}</td><td>${partyTag}</td>
        <td class="schools-cell">${ug}</td>
        <td>${escape(o._ug_field) || `<span class="deg">—</span>`}</td>
        <td class="schools-cell">${grad}</td>
        <td><span class="sector ${sectorClass}">${escape(sectorLabel)}</span></td>
      </tr>`;
    }).join("");
  }
  ["#q","#f-office","#f-state","#f-party","#f-sector","#f-degree"].forEach(s=>{$(s).addEventListener("input",apply);$(s).addEventListener("change",apply);});
  $("#reset").addEventListener("click",()=>{["#q","#f-office","#f-state","#f-party","#f-sector","#f-degree"].forEach(s=>{$(s).value="";});apply();});
  $$("thead th").forEach(th=>{th.addEventListener("click",()=>{const k=th.dataset.k;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1;}$$("thead th .arr").forEach(a=>a.textContent="");th.querySelector(".arr").textContent=sortDir>0?"▲":"▼";apply();});});
  document.querySelector('thead th[data-k="name"] .arr').textContent="▲";
  $("#refreshed").textContent = new Date().toISOString().slice(0,10);
  apply();
})();
