"""Bounded, server-filtered secure Inbox listings for growing WhatsApp traffic.

The legacy listing fetches the latest conversation for EVERY customer and
filters in Python. This limits payloads to 250 newest relevant conversations
and searches in SQL. Direct customer conversation URLs remain unchanged.
Read-only; original listing is used if the replacement query fails.
"""
LIMIT = 250

INBOX_QUERY = """
WITH latest AS (
    SELECT DISTINCT ON (c.customer_number)
      c.customer_number, c.role, c.content, c.sender_label, c.created_at, c.id
    FROM conversations c
    ORDER BY c.customer_number, c.created_at DESC, c.id DESC
)
SELECT c.customer_number, c.role, c.content, c.sender_label, c.created_at,
       COALESCE(a.ai_paused,FALSE) AS ai_paused,
       COALESCE(l.customer_name,'WhatsApp Customer') AS customer_name
FROM latest c
LEFT JOIN ai_takeover_state a ON a.customer_number = c.customer_number
LEFT JOIN LATERAL (
    SELECT NULLIF(x.customer_name,'') AS customer_name
    FROM leads x
    WHERE x.customer_number = c.customer_number
      AND x.merged_into_lead_id IS NULL AND x.privacy_deleted_at IS NULL
    ORDER BY x.updated_at DESC, x.id DESC
    LIMIT 1
) l ON TRUE
WHERE (
    %s = ''
    OR POSITION(%s IN LOWER(COALESCE(l.customer_name,'WhatsApp Customer'))) > 0
    OR POSITION(%s IN LOWER(c.customer_number)) > 0
    OR POSITION(%s IN LOWER(COALESCE(c.content,''))) > 0
)
ORDER BY COALESCE(a.ai_paused,FALSE) DESC, c.created_at DESC NULLS LAST,
         c.customer_number
LIMIT %s
"""


def load_inbox_customers(db_factory, search_query, local_timezone):
    needle = str(search_query or "").strip().casefold()[:120]
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(INBOX_QUERY, (needle, needle, needle, needle, LIMIT))
            rows=cur.fetchall()
    items=[]
    for customer_number,role,content,sender_label,created_at,ai_paused,customer_name in rows:
        local_time=(created_at.astimezone(local_timezone).strftime("%d %b %Y at %H:%M")
                    if created_at else "")
        preview=" ".join(str(content or "").split())
        if len(preview)>150:
            preview=preview[:147]+"..."
        items.append({
            "customer_number":customer_number,
            "customer_name":customer_name,
            "role":role,
            "sender_label":sender_label or ("AI Assistant" if role=="assistant" else "Customer"),
            "preview":preview,
            "created_at":created_at,
            "local_time":local_time,
            "ai_paused":bool(ai_paused),
        })
    return items


def install_inbox_query_efficiency(flask_app):
    """Replace only the admin's read-only index; existing private chats untouched."""
    view = getattr(flask_app,"view_functions",{}).get("admin_inbox")
    if view is None:
        return False
    ns=view.__globals__
    required=("get_db","get_admin_inbox_customers","ADMIN_TIMEZONE")
    if not callable(ns.get("get_db")) or not callable(ns.get("get_admin_inbox_customers")) or not ns.get("ADMIN_TIMEZONE"):
        return False
    original=ns["get_admin_inbox_customers"]
    if getattr(original,"_ibrows_bounded_inbox",False):
        return True

    def optimized(search_query=""):
        try:
            return load_inbox_customers(ns["get_db"],search_query,ns["ADMIN_TIMEZONE"])
        except Exception as exc:
            print("IBROWS INBOX EFFICIENCY: read-only fallback ("
                  +type(exc).__name__+")",flush=True)
            return original(search_query)
    optimized._ibrows_bounded_inbox=True
    ns["get_admin_inbox_customers"]=optimized

    # Show the cap honestly rather than implying these are ALL customers.
    template=ns.get("INBOX_TEMPLATE")
    anchor='<div class="tools"><form class="search"'
    if isinstance(template,str) and anchor in template and "ibrows-inbox-bounded-list" not in template:
        note=('<p class="sub" data-audit="ibrows-inbox-bounded-list">'
              'Showing up to the 250 most recent matching conversations, with '
              'human takeovers first. Search by customer name or number to '
              'find earlier chats. No records are deleted.</p>\n')
        ns["INBOX_TEMPLATE"]=template.replace(anchor,note+anchor,1)
    print("IBROWS INBOX EFFICIENCY: bounded read-only admin search enabled",flush=True)
    return True
