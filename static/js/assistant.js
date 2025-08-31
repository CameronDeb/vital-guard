console.log("🔍 Assistant JS loaded");

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("checkBtn");
  const area = document.getElementById("symptoms");
  const result = document.getElementById("result");
  const badge = document.getElementById("urgencyBadge");
  const spec = document.getElementById("spec");
  const adviceList = document.getElementById("adviceList");
  const lifeList = document.getElementById("lifeList");
  const disc = document.getElementById("disc");
  const doctorSearch = document.getElementById("doctorSearch");
  const doctorLink = document.getElementById("doctorLink");

  console.log("Elements check:", {
    btn: !!btn,
    area: !!area,
    result: !!result
  });

  if (!btn || !area) {
    console.error("❌ Required elements missing!");
    return;
  }

  btn.addEventListener("click", async () => {
    console.log("🔥 Button clicked!");
    
    const symptoms = area.value.trim();
    console.log("Symptoms:", symptoms);
    
    if (!symptoms) {
      alert("Please enter your symptoms");
      return;
    }
    
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    
    try {
      console.log("🚀 Making fetch request...");
      
      const response = await fetch("/api/health-assistant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          symptoms: symptoms
        })
      });
      
      console.log("Response status:", response.status);
      console.log("Response ok:", response.ok);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Got response:", data);
      
      // Show results
      if (result) {
        result.classList.remove("hide");
        
        if (badge) badge.textContent = (data.urgency || "low").toUpperCase();
        if (spec) spec.textContent = data.suggested_specialty || "Primary Care";
        if (disc) disc.textContent = data.disclaimer || "Educational only";
        
        // Clear and populate advice
        if (adviceList) {
          adviceList.innerHTML = "";
          (data.advice || []).forEach(advice => {
            const li = document.createElement("li");
            li.textContent = advice;
            adviceList.appendChild(li);
          });
        }
        
        // Clear and populate lifestyle
        if (lifeList) {
          lifeList.innerHTML = "";
          (data.lifestyle || []).forEach(tip => {
            const li = document.createElement("li");
            li.textContent = tip;
            lifeList.appendChild(li);
          });
        }
        
        // Doctor search link
        if (doctorSearch && doctorLink && data.google_search_link) {
          doctorSearch.classList.remove("hide");
          doctorLink.href = data.google_search_link;
        } else if (doctorSearch) {
          doctorSearch.classList.add("hide");
        }
        
        // Style urgency badge
        if (badge) {
          badge.style.background = data.urgency === "emergency" ? "#dc2626" :
                                   data.urgency === "high" ? "#ea580c" :
                                   data.urgency === "medium" ? "#d97706" : "#059669";
          badge.style.color = "#ffffff";
        }
      }
      
    } catch (error) {
      console.error("❌ Error:", error);
      alert(`Error: ${error.message}`);
      
      if (result) {
        result.classList.remove("hide");
        result.innerHTML = `<div style="color: red; padding: 20px;">
          Error: ${error.message}<br>
          Check the console for more details.
        </div>`;
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "Get AI Guidance";
    }
  });
});