// 다크모드 토글 버튼(있는 페이지만) 공용 로직. 저장된/시스템 테마 적용 자체는
// FOUC 방지를 위해 각 템플릿의 인라인 <script>(<style> 이전)가 담당함.
function toggleTheme() {
  var root = document.documentElement;
  var isDark = (root.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  var next = isDark ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) {}
  var btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}
(function () {
  var root = document.documentElement;
  var isDark = (root.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  var btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = isDark ? '☀️' : '🌙';
})();
