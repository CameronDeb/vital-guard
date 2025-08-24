document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".site-header");
  const onScroll = () => {
    header.style.boxShadow = window.scrollY > 8 ? "0 10px 24px rgba(0,0,0,.06)" : "none";
  };
  window.addEventListener("scroll", onScroll);
  onScroll();
});
