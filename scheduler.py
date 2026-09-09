"""Exact maximum-coverage, minimum-cost weekly assignment using residual flow."""
from collections import deque
from datetime import timedelta

ROLES = {"counter": "櫃檯", "technician": "技師", "reception": "現場接待"}


def generate(employees, leaves, monday, settings, history=None, fixed=None, open_days=None):
    history = history or {}
    days = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    unavailable = {(leave["employee_id"], day) for leave in leaves for day in days
                   if leave["start_date"] <= day <= leave["end_date"]}
    fixed = fixed or []
    assignments = list(fixed)
    open_days = set(days) if open_days is None else set(open_days)
    for role in ROLES:
        staff = [e for e in employees if e["active"] and e["role"] == role]
        n = len(staff)
        source, sink = n + 7, n + 8
        graph = [[] for _ in range(n + 9)]

        def edge(a, b, cap, cost):
            forward = [b, len(graph[b]), cap, cost]
            reverse = [a, len(graph[a]), 0, -cost]
            graph[a].append(forward)
            graph[b].append(reverse)
            return forward

        links = []
        for i, person in enumerate(staff):
            # Convex costs prioritize balanced weekly loads, then recent workloads.
            used = sum(a["employee_id"] == person["id"] for a in fixed)
            for shift in range(used, settings["max_days"]):
                edge(source, i, 1, shift * 1000 + history.get(person["id"], 0) * 10)
            rotation = (monday.toordinal() // 7 + i * 2) % 7
            for offset in range(7):
                d = (offset + rotation) % 7
                if days[d] in open_days and (person["id"], days[d]) not in unavailable:
                    link = edge(i, n + d, 1, offset)
                    links.append((person["id"], days[d], link))
        for d in range(7):
            fixed_ids = {e["id"] for e in employees if e["role"] == role}
            filled = sum(a["date"] == days[d] and a["employee_id"] in fixed_ids for a in fixed)
            edge(n + d, sink, max(0, settings["needs"][role] - filled), 0)
        while True:
            distance = [float("inf")] * len(graph)
            parent = [None] * len(graph)
            distance[source] = 0
            queue, queued = deque([source]), {source}
            while queue:
                a = queue.popleft()
                queued.remove(a)
                for j, (b, _, capacity, cost) in enumerate(graph[a]):
                    if capacity and distance[b] > distance[a] + cost:
                        distance[b] = distance[a] + cost
                        parent[b] = (a, j)
                        if b not in queued:
                            queued.add(b)
                            queue.append(b)
            if parent[sink] is None:
                break
            b = sink
            while b != source:
                a, j = parent[b]
                item = graph[a][j]
                item[2] -= 1
                graph[b][item[1]][2] += 1
                b = a
        assignments.extend({"employee_id": pid, "date": day} for pid, day, link in links if link[2] == 0)
    return assignments
