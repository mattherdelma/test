// 通用工具
window.AccApp = {
    // 通用 echarts 主题色
    colors: ['#1f4e79', '#e67e22', '#27ae60', '#c0392b', '#8e44ad', '#16a085', '#f39c12', '#2980b9', '#d35400', '#7f8c8d'],

    fetchJSON: async function(url) {
        const r = await fetch(url);
        if (!r.ok) throw new Error('请求失败');
        return await r.json();
    },

    formatMoney: function(v) {
        if (v == null) return '0';
        if (v >= 100000000) return (v / 100000000).toFixed(2) + ' 亿';
        if (v >= 10000) return (v / 10000).toFixed(2) + ' 万';
        return Number(v).toLocaleString();
    },

    renderYoY: function(v, inverse) {
        if (v == null) return '<span class="kpi-yoy">同比 —</span>';
        const cls = v > 0 ? 'up' : v < 0 ? 'down' : '';
        return `<span class="kpi-yoy ${cls}">同比 ${v > 0 ? '+' : ''}${v}%</span>`;
    },

    autoClose: function() {
        setTimeout(() => {
            document.querySelectorAll('.flash').forEach(el => {
                el.style.transition = 'opacity 0.4s';
                el.style.opacity = '0';
                setTimeout(() => el.remove(), 400);
            });
        }, 3000);
    },
};

document.addEventListener('DOMContentLoaded', AccApp.autoClose);
