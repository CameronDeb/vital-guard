const btn = document.getElementById("checkBtn");
const area = document.getElementById("symptoms");
const result = document.getElementById("result");
const badge = document.getElementById("urgencyBadge");
const spec = document.getElementById("spec");
const adviceList = document.getElementById("adviceList");
const lifeList = document.getElementById("lifeList");
const disc = document.getElementById("disc");

const coachBtn = document.getElementById("coachBtn");
const coachGoals = document.getElementById("coachGoals");
const coachOut = document.getElementById("coachOut");

btn.addEventListener("click", async () => {
  const symptoms = (area.value || "").trim();
  if (!symptoms) { area.focus(); return; }
  btn.disabled = true; btn.textContent = "Checking...";
  try{
    const resp = await fetch("/api/symptom-check", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ symptoms }) });
    const data = await resp.json();
    result.classList.remove("hide");
    adviceList.innerHTML = "";
    lifeList.innerHTML = "";
    badge.textContent = data.urgency || "low";
    spec.textContent = data.suggested_specialty || "primary care";
    (data.advice || []).forEach(a => { const li=document.createElement("li"); li.textContent=a; adviceList.appendChild(li); });
    (data.lifestyle || []).forEach(a => { const li=document.createElement("li"); li.textContent=a; lifeList.appendChild(li); });
    disc.textContent = data.disclaimer || "";
    if (data.urgency === "emergency"){ badge.style.background = "#b91c1c"; }
    else if (data.urgency === "high"){ badge.style.background = "#f97316"; }
    else { badge.style.background = "var(--accent)"; }
  } catch(e){ alert("Something went wrong. Please try again."); }
  finally{ btn.disabled = false; btn.textContent = "Check now"; }
});

if (coachBtn){
  coachBtn.addEventListener("click", async () => {
    coachBtn.disabled = true; coachBtn.textContent = "Generating...";
    coachOut.textContent = "";
    try{
      const resp = await fetch("/api/coach-plan", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ goals: coachGoals.value }) });
      const data = await resp.json();
      if (data.ok){ coachOut.textContent = data.plan; } else { coachOut.textContent = "Failed to generate plan."; }
    }catch(e){ coachOut.textContent = "Error generating plan."; }
    finally{ coachBtn.disabled = false; coachBtn.textContent = "Generate plan"; }
  });
}
