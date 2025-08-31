document.addEventListener("DOMContentLoaded", () => {
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

  if (btn && area) {
    btn.addEventListener("click", async () => {
      const symptoms = (area.value || "").trim();
      if (!symptoms) { 
        area.focus(); 
        return; 
      }
      
      btn.disabled = true; 
      btn.textContent = "Checking...";
      result.classList.add("hide");
      
      try {
        // Try the new endpoint first, fallback to old one
        let resp;
        try {
          resp = await fetch("/api/health-assistant", { 
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify({ symptoms, query: "" })
          });
        } catch (e) {
          // Fallback to legacy endpoint
          resp = await fetch("/api/symptom-check", { 
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify({ symptoms })
          });
        }

        if (!resp.ok) {
          throw new Error(`Server error: ${resp.status}`);
        }

        const data = await resp.json();
        
        result.classList.remove("hide");
        adviceList.innerHTML = "";
        lifeList.innerHTML = "";
        
        badge.textContent = (data.urgency || "low").toUpperCase();
        spec.textContent = data.suggested_specialty || "Primary Care";
        
        (data.advice || []).forEach(a => { 
          const li = document.createElement("li"); 
          li.textContent = a; 
          adviceList.appendChild(li); 
        });
        
        (data.lifestyle || []).forEach(a => { 
          const li = document.createElement("li"); 
          li.textContent = a; 
          lifeList.appendChild(li); 
        });
        
        disc.textContent = data.disclaimer || "Educational information only.";
        
        // Style badge based on urgency
        if (data.urgency === "emergency") { 
          badge.style.background = "#dc2626"; 
        } else if (data.urgency === "high") { 
          badge.style.background = "#ea580c"; 
        } else if (data.urgency === "medium") {
          badge.style.background = "#d97706";
        } else { 
          badge.style.background = "#059669"; 
        }
        
      } catch(e) { 
        alert(`Something went wrong: ${e.message}. Please try again.`); 
        console.error("Symptom check error:", e);
      } finally { 
        btn.disabled = false; 
        btn.textContent = "Check now"; 
      }
    });
  }

  // Health Coach functionality
  if (coachBtn && coachGoals && coachOut) {
    coachBtn.addEventListener("click", async () => {
      coachBtn.disabled = true; 
      coachBtn.textContent = "Generating...";
      coachOut.textContent = "";
      
      try {
        const resp = await fetch("/api/coach-plan", { 
          method: "POST", 
          headers: {"Content-Type": "application/json"}, 
          body: JSON.stringify({ goals: coachGoals.value || "General wellness" })
        });
        
        if (!resp.ok) {
          throw new Error(`Server error: ${resp.status}`);
        }
        
        const data = await resp.json();
        
        if (data.ok && data.plan) { 
          coachOut.textContent = data.plan; 
          coachOut.style.whiteSpace = "pre-wrap";
          coachOut.style.background = "#f8fafc";
          coachOut.style.padding = "16px";
          coachOut.style.borderRadius = "8px";
          coachOut.style.border = "1px solid #e2e8f0";
        } else { 
          coachOut.textContent = data.plan || "Failed to generate plan."; 
        }
        
      } catch(e) { 
        coachOut.textContent = `Error generating plan: ${e.message}`; 
        console.error("Coach plan error:", e);
      } finally { 
        coachBtn.disabled = false; 
        coachBtn.textContent = "Generate plan"; 
      }
    });
  }
});