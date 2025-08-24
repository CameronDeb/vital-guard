(async function(){
  if (!window.STRIPE_KEY || !window.PRICE_ID) return;
  const buy = document.getElementById("buyBtn");
  if (!buy) return;
  const stripe = Stripe(window.STRIPE_KEY);
  buy.addEventListener("click", async () => {
    buy.disabled = true;
    const res = await fetch("/api/create-checkout-session", { method:"POST" });
    const data = await res.json();
    if (data.id){
      const { error } = await stripe.redirectToCheckout({ sessionId: data.id });
      if (error) document.getElementById("status").textContent = error.message || "Checkout error";
    }else{
      document.getElementById("status").textContent = data.error || "Billing not configured";
    }
    buy.disabled = false;
  });
})();
