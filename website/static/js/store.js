// Animate product cards on scroll
if ('IntersectionObserver' in window) {
  const cards = document.querySelectorAll('.product-card');
  const obs = new IntersectionObserver(entries => {
    entries.forEach((e, i) => {
      if (e.isIntersecting) {
        setTimeout(() => e.target.style.opacity = '1', i * 60);
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  cards.forEach(c => { c.style.opacity = '0'; c.style.transition = 'opacity 0.5s ease'; obs.observe(c); });
}

// Buy button loading state
document.querySelectorAll('form[action^="/checkout"]').forEach(form => {
  form.addEventListener('submit', e => {
    const btn = form.querySelector('button[type=submit]');
    btn.textContent = '⏳  Redirecting to secure checkout…';
    btn.disabled = true;
  });
});
