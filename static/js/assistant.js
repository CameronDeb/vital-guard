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

  btn.addEventListener("click", async () => {
    const symptoms = (area.value || "").trim();
    if (!symptoms) {
      area.focus();
      return;
    }
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    result.classList.add("hide");

    try {
      const resp = await fetch("/api/health-assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptoms: symptoms, query: "" }), // Query is empty for now, can be expanded later
      });

      if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.error || "An unknown error occurred.");
      }
      
      const data = await resp.json();
      
      renderResults(data);

    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "Get AI Guidance";
    }
  });

  function renderResults(data) {
    result.classList.remove("hide");
    adviceList.innerHTML = "";
    lifeList.innerHTML = "";

    badge.textContent = data.urgency || "low";
    spec.textContent = data.suggested_specialty || "Primary Care";
    disc.textContent = data.disclaimer || "";

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

    if (data.google_search_link) {
        doctorSearch.classList.remove("hide");
        doctorLink.href = data.google_search_link;
    } else {
        doctorSearch.classList.add("hide");
    }

    // Style badge based on urgency
    badge.style.background = "var(--accent)"; // default
    if (data.urgency === "emergency") {
      badge.style.background = "#b91c1c";
    } else if (data.urgency === "high") {
      badge.style.background = "#f97316";
    } else if (data.urgency === "medium") {
        badge.style.background = "#f59e0b";
    }
  }
});
