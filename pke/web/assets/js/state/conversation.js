export function groupConversations(items, now = new Date()) {
  const groups = [
    { id: "today", label: "Hoje", items: [] },
    { id: "yesterday", label: "Ontem", items: [] },
    { id: "week", label: "Últimos 7 dias", items: [] },
    { id: "older", label: "Mais antigas", items: [] },
  ];
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today = startOfDay(now);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const week = new Date(today);
  week.setDate(today.getDate() - 7);
  for (const item of items) {
    const at = startOfDay(new Date(item.updated_at));
    if (at >= today) groups[0].items.push(item);
    else if (at >= yesterday) groups[1].items.push(item);
    else if (at >= week) groups[2].items.push(item);
    else groups[3].items.push(item);
  }
  return groups.filter((g) => g.items.length);
}

export function routeFromPath(pathname) {
  if (pathname === "/settings") return { name: "settings" };
  const match = pathname.match(/^\/c\/([^/]+)$/);
  if (match) return { name: "conversation", id: match[1] };
  return { name: "home" };
}
