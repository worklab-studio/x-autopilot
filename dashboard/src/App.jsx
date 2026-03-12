import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Area, AreaChart
} from "recharts";

// ─── THEME ───────────────────────────────────────────
const T = {
  bg: "#0a0a0a",
  surface: "#111111",
  border: "#1e1e1e",
  borderBright: "#2a2a2a",
  accent: "#00ff88",
  accentDim: "#00ff8820",
  accentMid: "#00ff8840",
  text: "#e8e8e8",
  textMid: "#888888",
  textDim: "#444444",
  red: "#ff4444",
  yellow: "#ffcc00",
  blue: "#4488ff",
};

// ─── ACTION TYPE CONFIG ──────────────────────────────
const ACTION_CONFIG = {
  tweet: { label: "TWEET", color: T.accent, icon: "✦" },
  tweet_generated: { label: "QUEUED", color: T.yellow, icon: "◈" },
  reply: { label: "REPLY", color: T.blue, icon: "↩" },
  follow: { label: "FOLLOW", color: "#cc88ff", icon: "+" },
  unfollow: { label: "UNFOLLOW", color: T.textMid, icon: "−" },
  dm: { label: "DM", color: "#ff8844", icon: "◉" },
  like: { label: "LIKE", color: "#ff4488", icon: "♥" },
};

const TIER_COLORS = {
  small: "#00ff88",
  peer: "#4488ff",
  big: "#ffcc00",
};

// ─── API HELPERS ─────────────────────────────────────
const api = {
  get: (path) => fetch(`/api${path}`).then(r => r.json()).catch(() => null),
  post: (path, body) => fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json()).catch(() => null),
};

// ─── COMPONENTS ──────────────────────────────────────

function StatBox({ label, value, accent }) {
  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      padding: "16px 20px",
      minWidth: 90,
    }}>
      <div style={{
        fontSize: 28,
        fontWeight: 700,
        color: accent || T.accent,
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: -1,
      }}>{value ?? "—"}</div>
      <div style={{
        fontSize: 10,
        color: T.textMid,
        letterSpacing: 2,
        marginTop: 4,
        fontFamily: "'JetBrains Mono', monospace",
      }}>{label}</div>
    </div>
  );
}

function AgentStatus({ paused, onPause, onResume, onQuit }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: paused ? T.red : T.accent,
          boxShadow: paused ? `0 0 8px ${T.red}` : `0 0 8px ${T.accent}`,
          animation: paused ? "none" : "pulse 2s infinite",
        }} />
        <span style={{
          fontSize: 11,
          letterSpacing: 2,
          color: paused ? T.red : T.accent,
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {paused ? "PAUSED" : "LIVE"}
        </span>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <button
          onClick={paused ? onResume : onPause}
          style={{
            background: "transparent",
            border: `1px solid ${paused ? T.accent : T.red}`,
            color: paused ? T.accent : T.red,
            padding: "6px 14px",
            fontSize: 11,
            letterSpacing: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {paused ? "RESUME" : "PAUSE"}
        </button>
        <button
          onClick={onQuit}
          style={{
            background: "transparent",
            border: `1px solid ${T.red}`,
            color: T.red,
            padding: "6px 14px",
            fontSize: 11,
            letterSpacing: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "var(--t-red-alpha-hover, rgba(255, 68, 68, 0.15))";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "transparent";
          }}
        >
          QUIT
        </button>
      </div>
    </div>
  );
}

function LiveFeed({ actions }) {
  const feedRef = useRef(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  }, [actions]);

  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
    }}>
      <div style={{
        padding: "14px 20px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <span style={{ fontSize: 11, letterSpacing: 3, color: T.textMid, fontFamily: "'JetBrains Mono', monospace" }}>
          LIVE ACTIVITY
        </span>
        <span style={{ fontSize: 10, color: T.textDim, fontFamily: "'JetBrains Mono', monospace" }}>
          {actions.length} events
        </span>
      </div>

      <div
        ref={feedRef}
        style={{
          overflowY: "auto",
          flex: 1,
          padding: "8px 0",
        }}
      >
        {actions.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center", color: T.textDim, fontSize: 12 }}>
            Waiting for activity...
          </div>
        ) : (
          actions.map((action, i) => {
            const cfg = ACTION_CONFIG[action.action_type] || { label: action.action_type.toUpperCase(), color: T.textMid, icon: "·" };
            const time = action.timestamp ? action.timestamp.substring(11, 16) : "";
            const tier = action.tier;

            return (
              <div key={i} style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                padding: "10px 20px",
                borderBottom: `1px solid ${T.border}`,
                opacity: action.success ? 1 : 0.5,
                transition: "background 0.2s",
              }}
                onMouseEnter={e => e.currentTarget.style.background = "#161616"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                {/* Time */}
                <span style={{
                  fontSize: 11,
                  color: T.textDim,
                  fontFamily: "'JetBrains Mono', monospace",
                  minWidth: 42,
                  marginTop: 1,
                }}>{time}</span>

                {/* Action type badge */}
                <span style={{
                  fontSize: 10,
                  color: cfg.color,
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: 1,
                  minWidth: 70,
                  marginTop: 1,
                }}>
                  {cfg.icon} {cfg.label}
                </span>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  {action.target_user && (
                    <span style={{
                      fontSize: 12,
                      color: T.text,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}>@{action.target_user} </span>
                  )}
                  {tier && (
                    <span style={{
                      fontSize: 9,
                      color: TIER_COLORS[tier] || T.textMid,
                      border: `1px solid ${TIER_COLORS[tier] || T.textMid}`,
                      padding: "1px 5px",
                      letterSpacing: 1,
                      marginRight: 6,
                    }}>{tier.toUpperCase()}</span>
                  )}
                  {action.content && (
                    <div style={{
                      fontSize: 11,
                      color: T.textMid,
                      marginTop: 3,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}>"{action.content}"</div>
                  )}
                </div>

                {/* Success indicator */}
                <span style={{
                  fontSize: 10,
                  color: action.success ? T.accent : T.red,
                  marginTop: 1,
                }}>
                  {action.success ? "✓" : "✗"}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function TweetCard({
  tweet,
  onApprove,
  onSkip,
  onRegenerate,
  onMediaUpload,
  onMediaRemove,
  threadIndex,
  threadTotal,
}) {
  const [editing, setEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(tweet.content);
  const [loading, setLoading] = useState(false);
  const [mediaLoading, setMediaLoading] = useState(false);
  const fileInputRef = useRef(null);
  const charCount = editedContent.length;
  const overLimit = charCount > 280;
  const isEmpty = editedContent.trim().length === 0;
  const mediaLabel = tweet.media_path ? tweet.media_path.split("/").pop() : "";

  const handleApprove = async () => {
    setLoading(true);
    await onApprove(tweet.id, editing ? editedContent : null);
    setLoading(false);
  };

  const handleRegenerate = async () => {
    setLoading(true);
    const result = await onRegenerate(tweet.id);
    if (result?.content) {
      setEditedContent(result.content);
    }
    setLoading(false);
  };

  const scheduledLabel = tweet.scheduled_for
    ? (() => {
      const parsed = Date.parse(tweet.scheduled_for);
      if (!Number.isNaN(parsed)) {
        return new Date(parsed).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      }
      return tweet.scheduled_for;
    })()
    : null;
  const displayContent = tweet.content && tweet.content.trim()
    ? tweet.content
    : "Click to write the next tweet...";

  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.borderBright}`,
      padding: 20,
      display: "flex",
      flexDirection: "column",
      gap: 14,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontSize: 9,
            letterSpacing: 2,
            color: T.yellow,
            border: `1px solid ${T.yellow}`,
            padding: "2px 8px",
            fontFamily: "'JetBrains Mono', monospace",
          }}>PENDING APPROVAL</span>
          {threadIndex && threadTotal && (
            <span style={{
              fontSize: 9,
              letterSpacing: 1,
              color: T.textDim,
              border: `1px solid ${T.borderBright}`,
              padding: "2px 6px",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              THREAD {threadIndex}/{threadTotal}
            </span>
          )}
          {scheduledLabel && (
            <span style={{ fontSize: 10, color: T.textMid, fontFamily: "'JetBrains Mono', monospace" }}>
              → {scheduledLabel}
            </span>
          )}
        </div>
        <span style={{
          fontSize: 10,
          color: overLimit ? T.red : T.textMid,
          fontFamily: "'JetBrains Mono', monospace",
        }}>{charCount}/280</span>
      </div>

      {/* Content */}
      {editing ? (
        <textarea
          value={editedContent}
          onChange={e => setEditedContent(e.target.value)}
          style={{
            background: "#0d0d0d",
            border: `1px solid ${T.accent}`,
            color: T.text,
            padding: 14,
            fontSize: 14,
            lineHeight: 1.6,
            resize: "vertical",
            minHeight: 100,
            fontFamily: "Georgia, serif",
            outline: "none",
          }}
          autoFocus
        />
      ) : (
        <div
          style={{
            fontSize: 14,
            color: displayContent === tweet.content ? T.text : T.textDim,
            lineHeight: 1.7,
            fontFamily: "Georgia, serif",
            cursor: "text",
            padding: "12px 14px",
            background: "#0d0d0d",
            border: `1px solid ${T.border}`,
            whiteSpace: "pre-wrap",
          }}
          onClick={() => setEditing(true)}
        >
          {displayContent}
        </div>
      )}

      {/* Media */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{
          fontSize: 9,
          letterSpacing: 2,
          color: T.textDim,
          border: `1px solid ${T.borderBright}`,
          padding: "2px 6px",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          MEDIA
        </span>
        {mediaLabel ? (
          <span style={{
            fontSize: 10,
            color: T.textMid,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {tweet.media_type ? `${tweet.media_type.toUpperCase()}: ` : ""}{mediaLabel}
          </span>
        ) : (
          <span style={{
            fontSize: 10,
            color: T.textDim,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            none
          </span>
        )}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={mediaLoading}
          style={{
            background: "transparent",
            border: `1px solid ${T.borderBright}`,
            color: T.textMid,
            padding: "6px 10px",
            fontSize: 9,
            letterSpacing: 1,
            cursor: mediaLoading ? "not-allowed" : "pointer",
            fontFamily: "'JetBrains Mono', monospace",
            opacity: mediaLoading ? 0.6 : 1,
          }}
        >
          {mediaLoading ? "UPLOADING..." : "ADD MEDIA"}
        </button>
        {mediaLabel && (
          <button
            onClick={async () => {
              setMediaLoading(true);
              await onMediaRemove(tweet.id);
              setMediaLoading(false);
            }}
            disabled={mediaLoading}
            style={{
              background: "transparent",
              border: `1px solid ${T.border}`,
              color: T.textDim,
              padding: "6px 10px",
              fontSize: 9,
              letterSpacing: 1,
              cursor: mediaLoading ? "not-allowed" : "pointer",
              fontFamily: "'JetBrains Mono', monospace",
              opacity: mediaLoading ? 0.6 : 1,
            }}
          >
            REMOVE
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          style={{ display: "none" }}
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setMediaLoading(true);
            await onMediaUpload(tweet.id, file);
            setMediaLoading(false);
            e.target.value = "";
          }}
        />
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={handleApprove}
          disabled={loading || overLimit || isEmpty}
          style={{
            flex: 1,
            background: T.accentMid,
            border: `1px solid ${T.accent}`,
            color: T.accent,
            padding: "10px 0",
            fontSize: 11,
            letterSpacing: 2,
            cursor: loading || overLimit || isEmpty ? "not-allowed" : "pointer",
            fontFamily: "'JetBrains Mono', monospace",
            opacity: loading || overLimit || isEmpty ? 0.5 : 1,
          }}
        >
          {loading ? "..." : "✓ APPROVE"}
        </button>

        <button
          onClick={() => setEditing(!editing)}
          style={{
            background: "transparent",
            border: `1px solid ${T.borderBright}`,
            color: T.textMid,
            padding: "10px 16px",
            fontSize: 11,
            letterSpacing: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {editing ? "DONE" : "✎ EDIT"}
        </button>

        <button
          onClick={handleRegenerate}
          disabled={loading}
          style={{
            background: "transparent",
            border: `1px solid ${T.borderBright}`,
            color: T.textMid,
            padding: "10px 16px",
            fontSize: 11,
            letterSpacing: 2,
            cursor: loading ? "not-allowed" : "pointer",
            fontFamily: "'JetBrains Mono', monospace",
            opacity: loading ? 0.5 : 1,
          }}
        >
          ↺ NEW
        </button>

        <button
          onClick={() => onSkip(tweet.id)}
          style={{
            background: "transparent",
            border: `1px solid ${T.border}`,
            color: T.textDim,
            padding: "10px 16px",
            fontSize: 11,
            letterSpacing: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          ✗ SKIP
        </button>
      </div>
    </div>
  );
}

function ThreadGroup({ group, onApprove, onSkip, onRegenerate, onAddNext, onMediaUpload, onMediaRemove }) {
  const tweets = group.tweets || [];
  const total = tweets.length;
  const threadLabel = group.threadId ? "THREAD" : "SINGLE";

  return (
    <div style={{
      border: `1px solid ${T.borderBright}`,
      background: T.surface,
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{
          fontSize: 9,
          letterSpacing: 2,
          color: T.accent,
          border: `1px solid ${T.accent}`,
          padding: "2px 8px",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {threadLabel} {total > 1 ? total : ""}
        </span>
        <button
          onClick={() => onAddNext(tweets[0]?.id)}
          style={{
            marginLeft: "auto",
            background: "transparent",
            border: `1px solid ${T.borderBright}`,
            color: T.textMid,
            padding: "6px 12px",
            fontSize: 10,
            letterSpacing: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          ADD NEXT
        </button>
      </div>
      <div style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        position: "relative",
        paddingLeft: 12,
      }}>
        <div style={{
          position: "absolute",
          top: 6,
          bottom: 6,
          left: 2,
          width: 2,
          background: T.borderBright,
        }} />
        {tweets.map((tweet, index) => (
          <div key={tweet.id} style={{ position: "relative" }}>
            <div style={{
              position: "absolute",
              left: -14,
              top: 16,
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: index === 0 ? T.accent : T.textDim,
              boxShadow: index === 0 ? `0 0 8px ${T.accent}` : "none",
            }} />
            <TweetCard
              tweet={tweet}
              onApprove={onApprove}
              onSkip={onSkip}
              onRegenerate={onRegenerate}
              onMediaUpload={onMediaUpload}
              onMediaRemove={onMediaRemove}
              threadIndex={tweet.thread_index || index + 1}
              threadTotal={total}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function GrowthChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div style={{
        height: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: T.textDim,
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        Growth data will appear after first full day
      </div>
    );
  }

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload?.length) {
      return (
        <div style={{
          background: T.surface,
          border: `1px solid ${T.border}`,
          padding: "8px 12px",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
        }}>
          <div style={{ color: T.textMid }}>{label}</div>
          <div style={{ color: T.accent }}>{payload[0]?.value} followers</div>
        </div>
      );
    }
    return null;
  };

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="followersGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={T.accent} stopOpacity={0.3} />
            <stop offset="95%" stopColor={T.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
        <XAxis
          dataKey="date"
          tick={{ fill: T.textDim, fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
          tickFormatter={d => d?.substring(5)}
          stroke={T.border}
        />
        <YAxis
          tick={{ fill: T.textDim, fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
          stroke={T.border}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="followers"
          stroke={T.accent}
          strokeWidth={2}
          fill="url(#followersGradient)"
          dot={false}
          activeDot={{ r: 4, fill: T.accent, stroke: "none" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function TargetList({ label, items, onRemove }) {
  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      padding: 16,
      flex: 1,
      minWidth: 200,
    }}>
      <div style={{ fontSize: 10, letterSpacing: 2, color: T.textMid, marginBottom: 10 }}>
        {label}
      </div>
      {items.length === 0 ? (
        <div style={{ fontSize: 11, color: T.textDim }}>No accounts</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {items.map(name => (
            <div key={name} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, color: T.text }}>@{name}</span>
              <button
                onClick={() => onRemove(name)}
                style={{
                  marginLeft: "auto",
                  background: "transparent",
                  border: `1px solid ${T.borderBright}`,
                  color: T.textDim,
                  padding: "2px 6px",
                  fontSize: 9,
                  letterSpacing: 1,
                  cursor: "pointer",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                REMOVE
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HashtagList({ items, onRemove }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.length === 0 ? (
        <span style={{ fontSize: 11, color: T.textDim }}>No hashtags</span>
      ) : (
        items.map(tag => (
          <span key={tag} style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            border: `1px solid ${T.borderBright}`,
            padding: "4px 8px",
            fontSize: 10,
            color: T.textMid,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            #{tag}
            <button
              onClick={() => onRemove(tag)}
              style={{
                background: "transparent",
                border: "none",
                color: T.textDim,
                cursor: "pointer",
                fontSize: 10,
              }}
            >
              ×
            </button>
          </span>
        ))
      )}
    </div>
  );
}

function TierSelect({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const options = [
    { value: "small", label: "0–1k" },
    { value: "peer", label: "1k–10k" },
    { value: "big", label: "10k+" },
  ];

  useEffect(() => {
    const handleClick = (event) => {
      if (!wrapperRef.current || !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const selected = options.find(o => o.value === value) || options[0];

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        type="button"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "#0d0d0d",
          border: `1px solid ${T.borderBright}`,
          color: T.textMid,
          padding: "8px 10px",
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          cursor: "pointer",
          minWidth: 90,
        }}
      >
        {selected.label}
        <span style={{ marginLeft: "auto", color: T.textDim }}>▾</span>
      </button>
      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 6px)",
          left: 0,
          background: "#0d0d0d",
          border: `1px solid ${T.borderBright}`,
          boxShadow: "0 8px 20px rgba(0,0,0,0.5)",
          zIndex: 20,
          minWidth: 120,
        }}>
          {options.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              style={{
                display: "flex",
                width: "100%",
                background: option.value === value ? T.accentMid : "transparent",
                border: "none",
                color: option.value === value ? T.accent : T.textMid,
                padding: "8px 10px",
                fontSize: 11,
                fontFamily: "'JetBrains Mono', monospace",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SettingsSection({ title, children }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
      <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
        {title}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        {children}
      </div>
    </div>
  );
}

function SettingsInput({ label, value, onChange, type = "text", placeholder, min, step }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 10, color: T.textDim, letterSpacing: 1 }}>{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        min={min}
        step={step}
        style={{
          background: "#0d0d0d",
          border: `1px solid ${T.borderBright}`,
          color: T.text,
          padding: "8px 10px",
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          outline: "none",
        }}
      />
    </label>
  );
}

function SettingsTextarea({ label, value, onChange, placeholder, rows = 4 }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6, gridColumn: "1 / -1" }}>
      <span style={{ fontSize: 10, color: T.textDim, letterSpacing: 1 }}>{label}</span>
      <textarea
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        style={{
          background: "#0d0d0d",
          border: `1px solid ${T.borderBright}`,
          color: T.text,
          padding: "8px 10px",
          fontSize: 11,
          lineHeight: 1.5,
          fontFamily: "'JetBrains Mono', monospace",
          outline: "none",
          resize: "vertical",
        }}
      />
    </label>
  );
}

function SettingsToggle({ label, checked, onChange }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <input
        type="checkbox"
        checked={!!checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 14, height: 14 }}
      />
      <span style={{ fontSize: 10, color: T.textDim, letterSpacing: 1 }}>{label}</span>
    </label>
  );
}

// ─── MAIN APP ────────────────────────────────────────
export default function App() {
  const [actions, setActions] = useState([]);
  const [queue, setQueue] = useState([]);
  const [stats, setStats] = useState({});
  const [statsRange, setStatsRange] = useState("today");
  const [growth, setGrowth] = useState([]);
  const [paused, setPaused] = useState(false);
  const [activeTab, setActiveTab] = useState("feed");
  const [lastUpdate, setLastUpdate] = useState(null);
  const [trends, setTrends] = useState([]);
  const [voiceProfile, setVoiceProfile] = useState("");
  const [voiceSaved, setVoiceSaved] = useState(false);
  const [testTweet, setTestTweet] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadStatus, setThreadStatus] = useState("");
  const [threadError, setThreadError] = useState("");
  const [threadTopic, setThreadTopic] = useState("");
  const [targets, setTargets] = useState({ small: [], peer: [], big: [] });
  const [hashtags, setHashtags] = useState([]);
  const [newTarget, setNewTarget] = useState("");
  const [newTargetTier, setNewTargetTier] = useState("small");
  const [newHashtag, setNewHashtag] = useState("");
  const [promotions, setPromotions] = useState([]);
  const [promoName, setPromoName] = useState("");
  const [promoUrl, setPromoUrl] = useState("");
  const [promoContext, setPromoContext] = useState("");
  const [config, setConfig] = useState(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);
  const [configError, setConfigError] = useState("");

  const fetchAll = useCallback(async () => {
    const [a, q, s, g, state, t, v, targ, tags, promos] = await Promise.all([
      api.get("/actions?limit=60"),
      api.get("/queue"),
      api.get(`/stats?range=${statsRange}`),
      api.get("/growth"),
      api.get("/agent/state"),
      api.get("/trends"),
      api.get("/voice-profile"),
      api.get("/targets"),
      api.get("/hashtags"),
      api.get("/promotions"),
    ]);
    if (a) setActions(a);
    if (q) setQueue(q);
    if (s) setStats(s);
    if (g) setGrowth(g);
    if (state) setPaused(state.paused);
    if (t?.trends) setTrends(t.trends);
    if (v?.content && !voiceProfile) setVoiceProfile(v.content);
    if (targ) setTargets(targ);
    if (tags?.hashtags) setHashtags(tags.hashtags);
    if (promos?.promotions) setPromotions(promos.promotions);
    setLastUpdate(new Date().toLocaleTimeString());
  }, [voiceProfile, statsRange]);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  useEffect(() => {
    fetchAll();
  }, [statsRange, fetchAll]);

  useEffect(() => {
    const loadConfig = async () => {
      const cfg = await api.get("/config");
      if (cfg) setConfig(cfg);
    };
    loadConfig();
  }, []);

  const handleApprove = async (id, content) => {
    await api.post(`/queue/${id}/approve`, content ? { content } : null);
    fetchAll();
  };

  const handleSkip = async (id) => {
    await api.post(`/queue/${id}/skip`);
    fetchAll();
  };

  const handleRegenerate = async (id) => {
    const result = await api.post(`/queue/${id}/regenerate`);
    fetchAll();
    return result;
  };

  const handlePause = async () => {
    await api.post("/agent/pause");
    setPaused(true);
  };

  const handleResume = async () => {
    await api.post("/agent/resume");
    setPaused(false);
  };

  const handleQuit = async () => {
    if (window.confirm("Are you sure you want to stop the agent?")) {
      await api.post("/agent/quit");
      // Optionally stop polling or show a quit state
      setPaused(true);
    }
  };

  const handleSaveVoice = async () => {
    await api.post("/voice-profile", { content: voiceProfile });
    setVoiceSaved(true);
    setTimeout(() => setVoiceSaved(false), 2000);
  };

  const handleTestTweet = async (type = "auto") => {
    setTestLoading(true);
    setTestTweet(null);
    const result = await api.post("/test-tweet", { type });
    if (result?.content) setTestTweet(result.content);
    setTestLoading(false);
  };

  const handleGenerateThread = async () => {
    setThreadLoading(true);
    setThreadStatus("");
    setThreadError("");
    const topic = threadTopic.trim();
    const result = await api.post("/thread", topic ? { topic } : null);
    if (result?.success) {
      setThreadStatus(`Queued ${result.count} tweets about "${result.topic}"`);
      fetchAll();
    } else {
      setThreadError(result?.error || "Failed to generate thread");
    }
    setThreadLoading(false);
  };

  const handleAddThreadNext = async (tweetId) => {
    if (!tweetId) return;
    await api.post("/queue/thread/add-next", { tweet_id: tweetId, content: "" });
    fetchAll();
  };

  const updateConfigRoot = (key, value) => {
    setConfig(prev => ({
      ...(prev || {}),
      [key]: value,
    }));
  };

  const updateConfig = (section, key, value) => {
    setConfig(prev => ({
      ...(prev || {}),
      [section]: {
        ...((prev || {})[section]),
        [key]: value,
      },
    }));
  };

  const updateConfigTier = (tier, key, value) => {
    setConfig(prev => ({
      ...(prev || {}),
      tiers: {
        ...((prev || {}).tiers),
        [tier]: {
          ...(((prev || {}).tiers || {})[tier]),
          [key]: value,
        },
      },
    }));
  };

  const handleSaveConfig = async () => {
    if (!config) return;
    setConfigSaving(true);
    setConfigError("");
    const result = await api.post("/config", { config });
    if (result?.success) {
      setConfigSaved(true);
      setTimeout(() => setConfigSaved(false), 2000);
    } else {
      setConfigError(result?.error || "Failed to save settings");
    }
    setConfigSaving(false);
  };

  const handleMediaUpload = async (tweetId, file) => {
    if (!tweetId || !file) return;
    const formData = new FormData();
    formData.append("file", file);
    await fetch(`/api/queue/${tweetId}/media`, {
      method: "POST",
      body: formData,
    }).then(r => r.json()).catch(() => null);
    fetchAll();
  };

  const handleMediaRemove = async (tweetId) => {
    if (!tweetId) return;
    await api.post(`/queue/${tweetId}/media/remove`);
    fetchAll();
  };

  const handleAddTarget = async () => {
    const username = newTarget.trim();
    if (!username) return;
    await api.post("/targets/add", { username, tier: newTargetTier });
    setNewTarget("");
    fetchAll();
  };

  const handleRemoveTarget = async (username) => {
    await api.post("/targets/remove", { username });
    fetchAll();
  };

  const handleAddHashtag = async () => {
    const tag = newHashtag.trim();
    if (!tag) return;
    await api.post("/hashtags/add", { tag });
    setNewHashtag("");
    fetchAll();
  };

  const handleRemoveHashtag = async (tag) => {
    await api.post("/hashtags/remove", { tag });
    fetchAll();
  };

  const handleAddPromotion = async () => {
    if (!promoName.trim() || !promoUrl.trim() || !promoContext.trim()) return;
    await api.post("/promotions/add", {
      name: promoName.trim(),
      url: promoUrl.trim(),
      context: promoContext.trim(),
    });
    setPromoName("");
    setPromoUrl("");
    setPromoContext("");
    fetchAll();
  };

  const handleRemovePromotion = async (index) => {
    await api.post("/promotions/remove", { index });
    fetchAll();
  };

  const groupedQueue = (() => {
    const groups = [];
    const threadMap = new Map();
    queue.forEach(tweet => {
      if (tweet.thread_id) {
        if (!threadMap.has(tweet.thread_id)) {
          threadMap.set(tweet.thread_id, []);
        }
        threadMap.get(tweet.thread_id).push(tweet);
      } else {
        groups.push({
          id: `single-${tweet.id}`,
          threadId: null,
          tweets: [tweet],
          created_at: tweet.created_at,
        });
      }
    });

    for (const [threadId, tweets] of threadMap.entries()) {
      const sorted = [...tweets].sort((a, b) => {
        const ai = a.thread_index || 0;
        const bi = b.thread_index || 0;
        if (ai !== bi) return ai - bi;
        return new Date(a.created_at || 0) - new Date(b.created_at || 0);
      });
      groups.push({
        id: `thread-${threadId}`,
        threadId,
        tweets: sorted,
        created_at: sorted[0]?.created_at,
      });
    }

    return groups.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
  })();

  return (
    <div style={{
      background: T.bg,
      minHeight: "100vh",
      color: T.text,
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        button { transition: all 0.15s ease; }
        button:hover { filter: brightness(1.2); }
      `}</style>

      {/* Header */}
      <div style={{
        padding: "16px 28px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        position: "sticky",
        top: 0,
        background: T.bg,
        zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: 3, color: T.text }}>
              TWITTER AGENT
            </div>
            <div style={{ fontSize: 9, color: T.textDim, letterSpacing: 2, marginTop: 2 }}>
              GROWTH SYSTEM v2.0
            </div>
          </div>
          <div style={{ width: 1, height: 30, background: T.border }} />
          <AgentStatus paused={paused} onPause={handlePause} onResume={handleResume} onQuit={handleQuit} />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {lastUpdate && (
            <span style={{ fontSize: 10, color: T.textDim }}>
              updated {lastUpdate}
            </span>
          )}
        </div>
      </div>

      {/* Stats Bar */}
      <div style={{
        padding: "16px 28px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}>
        <div style={{ display: "flex", gap: 12, overflowX: "auto", flex: 1 }}>
          <StatBox
            label="TWEETS"
            value={statsRange === "today" ? `${stats.tweets || 0}/2` : (stats.tweets || 0)}
            accent={T.accent}
          />
          <StatBox label="REPLIES" value={stats.replies || 0} accent={T.blue} />
          <StatBox label="DMs" value={stats.dms || 0} accent="#ff8844" />
          <StatBox label="FOLLOWS" value={stats.follows || 0} accent="#cc88ff" />
          <StatBox label="LIKES" value={stats.likes || 0} accent="#ff4488" />
          <StatBox label="QUEUE" value={queue.length} accent={T.yellow} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {[
            { key: "today", label: "TODAY" },
            { key: "month", label: "MONTH" },
            { key: "all", label: "ALL TIME" },
          ].map(option => (
            <button
              key={option.key}
              onClick={() => setStatsRange(option.key)}
              style={{
                background: statsRange === option.key ? T.accentMid : "transparent",
                border: `1px solid ${statsRange === option.key ? T.accent : T.borderBright}`,
                color: statsRange === option.key ? T.accent : T.textMid,
                padding: "6px 10px",
                fontSize: 9,
                letterSpacing: 2,
                cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div style={{ display: "flex", height: "calc(100vh - 155px)" }}>

        {/* Left — Feed or Queue */}
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          borderRight: `1px solid ${T.border}`,
          minWidth: 0,
        }}>
          {/* Tabs */}
          <div style={{
            display: "flex",
            borderBottom: `1px solid ${T.border}`,
          }}>
            {[
              { key: "feed", label: "LIVE FEED" },
              { key: "queue", label: `APPROVAL QUEUE ${queue.length > 0 ? `(${queue.length})` : ""}` },
              { key: "voice", label: "VOICE LAB" },
              { key: "discovery", label: "DISCOVERY" },
              { key: "promotions", label: "PROMOTIONS" },
              { key: "settings", label: "SETTINGS" },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  background: "transparent",
                  border: "none",
                  borderBottom: `2px solid ${activeTab === tab.key ? T.accent : "transparent"}`,
                  color: activeTab === tab.key ? T.accent : T.textMid,
                  padding: "14px 24px",
                  fontSize: 10,
                  letterSpacing: 2,
                  cursor: "pointer",
                  fontFamily: "'JetBrains Mono', monospace",
                  marginBottom: -1,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {activeTab === "feed" ? (
              <LiveFeed actions={actions} />
            ) : activeTab === "voice" ? (
              <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>

                {/* Test tweet generator */}
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    TEST TWEET GENERATOR
                  </div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
                    {["auto", "hot_take", "build_update", "personal", "resource"].map(type => (
                      <button
                        key={type}
                        onClick={() => handleTestTweet(type)}
                        disabled={testLoading}
                        style={{
                          background: "transparent",
                          border: `1px solid ${T.borderBright}`,
                          color: T.textMid,
                          padding: "7px 14px",
                          fontSize: 10,
                          letterSpacing: 2,
                          cursor: testLoading ? "not-allowed" : "pointer",
                          fontFamily: "'JetBrains Mono', monospace",
                        }}
                      >
                        {type.replace("_", " ").toUpperCase()}
                      </button>
                    ))}
                  </div>

                  {testLoading && (
                    <div style={{ color: T.textMid, fontSize: 12, padding: "12px 0" }}>
                      ⏳ Generating...
                    </div>
                  )}

                  {testTweet && !testLoading && (
                    <div>
                      <div style={{
                        background: "#0d0d0d",
                        border: `1px solid ${T.accent}`,
                        padding: 16,
                        fontSize: 14,
                        color: T.text,
                        lineHeight: 1.7,
                        fontFamily: "Georgia, serif",
                        marginBottom: 10,
                        whiteSpace: "pre-wrap",
                      }}>
                        {testTweet}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10, color: T.textDim }}>{testTweet.length}/280 chars</span>
                        <button
                          onClick={async () => {
                            const result = await api.post("/queue/add", { content: testTweet });
                            if (result?.success) fetchAll();
                          }}
                          style={{
                            background: T.accentMid,
                            border: `1px solid ${T.accent}`,
                            color: T.accent,
                            padding: "6px 14px",
                            fontSize: 10,
                            letterSpacing: 2,
                            cursor: "pointer",
                            fontFamily: "'JetBrains Mono', monospace",
                          }}
                        >
                          + ADD TO QUEUE
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Thread generator */}
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    THREAD GENERATOR
                  </div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                    <input
                      value={threadTopic}
                      onChange={e => setThreadTopic(e.target.value)}
                      placeholder="Optional topic (leave blank for auto)"
                      style={{
                        flex: "1 1 240px",
                        background: "#0d0d0d",
                        border: `1px solid ${T.borderBright}`,
                        color: T.text,
                        padding: "8px 10px",
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                        outline: "none",
                      }}
                    />
                    <button
                      onClick={handleGenerateThread}
                      disabled={threadLoading}
                      style={{
                        background: "transparent",
                        border: `1px solid ${T.borderBright}`,
                        color: T.textMid,
                        padding: "7px 14px",
                        fontSize: 10,
                        letterSpacing: 2,
                        cursor: threadLoading ? "not-allowed" : "pointer",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      {threadLoading ? "GENERATING..." : "GENERATE THREAD"}
                    </button>
                  </div>
                  {threadStatus && (
                    <div style={{ fontSize: 11, color: T.accent, paddingTop: 6 }}>
                      {threadStatus}
                    </div>
                  )}
                  {threadError && (
                    <div style={{ fontSize: 11, color: T.red, paddingTop: 6 }}>
                      {threadError}
                    </div>
                  )}
                </div>

                {/* Voice profile editor */}
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20, flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid }}>
                      VOICE PROFILE EDITOR
                    </div>
                    <button
                      onClick={handleSaveVoice}
                      style={{
                        background: voiceSaved ? T.accentMid : "transparent",
                        border: `1px solid ${voiceSaved ? T.accent : T.borderBright}`,
                        color: voiceSaved ? T.accent : T.textMid,
                        padding: "6px 16px",
                        fontSize: 10,
                        letterSpacing: 2,
                        cursor: "pointer",
                        fontFamily: "'JetBrains Mono', monospace",
                        transition: "all 0.2s",
                      }}
                    >
                      {voiceSaved ? "✓ SAVED" : "SAVE"}
                    </button>
                  </div>
                  <div style={{ fontSize: 10, color: T.textDim, marginBottom: 12 }}>
                    Edit this file to change how the AI writes as you. Regenerate test tweets above to see the effect.
                  </div>
                  <textarea
                    value={voiceProfile}
                    onChange={e => setVoiceProfile(e.target.value)}
                    style={{
                      width: "100%",
                      minHeight: 400,
                      background: "#0d0d0d",
                      border: `1px solid ${T.border}`,
                      color: T.text,
                      padding: 16,
                      fontSize: 12,
                      lineHeight: 1.7,
                      fontFamily: "'JetBrains Mono', monospace",
                      resize: "vertical",
                      outline: "none",
                    }}
                  />
                </div>
              </div>
            ) : activeTab === "discovery" ? (
              <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    TARGET ACCOUNTS
                  </div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
                    <input
                      value={newTarget}
                      onChange={e => setNewTarget(e.target.value)}
                      placeholder="Username (without @)"
                      style={{
                        flex: "1 1 220px",
                        background: "#0d0d0d",
                        border: `1px solid ${T.borderBright}`,
                        color: T.text,
                        padding: "8px 10px",
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                        outline: "none",
                      }}
                    />
                    <TierSelect
                      value={newTargetTier}
                      onChange={setNewTargetTier}
                    />
                    <button
                      onClick={handleAddTarget}
                      style={{
                        background: "transparent",
                        border: `1px solid ${T.borderBright}`,
                        color: T.textMid,
                        padding: "7px 14px",
                        fontSize: 10,
                        letterSpacing: 2,
                        cursor: "pointer",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      ADD ACCOUNT
                    </button>
                  </div>

                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    <TargetList
                      label="0–1k"
                      items={targets.small || []}
                      onRemove={handleRemoveTarget}
                    />
                    <TargetList
                      label="1k–10k"
                      items={targets.peer || []}
                      onRemove={handleRemoveTarget}
                    />
                    <TargetList
                      label="10k+"
                      items={targets.big || []}
                      onRemove={handleRemoveTarget}
                    />
                  </div>
                </div>

                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    HASHTAG DISCOVERY
                  </div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                    <input
                      value={newHashtag}
                      onChange={e => setNewHashtag(e.target.value)}
                      placeholder="Hashtag (without #)"
                      style={{
                        flex: "1 1 220px",
                        background: "#0d0d0d",
                        border: `1px solid ${T.borderBright}`,
                        color: T.text,
                        padding: "8px 10px",
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                        outline: "none",
                      }}
                    />
                    <button
                      onClick={handleAddHashtag}
                      style={{
                        background: "transparent",
                        border: `1px solid ${T.borderBright}`,
                        color: T.textMid,
                        padding: "7px 14px",
                        fontSize: 10,
                        letterSpacing: 2,
                        cursor: "pointer",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      ADD HASHTAG
                    </button>
                  </div>
                  <HashtagList items={hashtags} onRemove={handleRemoveHashtag} />
                </div>
              </div>
            ) : activeTab === "promotions" ? (
              <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    PROMOTIONS
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                    <input
                      value={promoName}
                      onChange={e => setPromoName(e.target.value)}
                      placeholder="Product name"
                      style={{
                        flex: "1 1 160px",
                        background: "#0d0d0d",
                        border: `1px solid ${T.borderBright}`,
                        color: T.text,
                        padding: "8px 10px",
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                        outline: "none",
                      }}
                    />
                    <input
                      value={promoUrl}
                      onChange={e => setPromoUrl(e.target.value)}
                      placeholder="https://..."
                      style={{
                        flex: "1 1 200px",
                        background: "#0d0d0d",
                        border: `1px solid ${T.borderBright}`,
                        color: T.text,
                        padding: "8px 10px",
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                        outline: "none",
                      }}
                    />
                  </div>
                  <textarea
                    value={promoContext}
                    onChange={e => setPromoContext(e.target.value)}
                    placeholder="Context / paragraphs about the product (who it's for, why it exists, wins, learnings)"
                    style={{
                      width: "100%",
                      minHeight: 120,
                      background: "#0d0d0d",
                      border: `1px solid ${T.borderBright}`,
                      color: T.text,
                      padding: "10px 12px",
                      fontSize: 11,
                      lineHeight: 1.6,
                      fontFamily: "'JetBrains Mono', monospace",
                      outline: "none",
                      resize: "vertical",
                      marginBottom: 12,
                    }}
                  />
                  <button
                    onClick={handleAddPromotion}
                    style={{
                      background: "transparent",
                      border: `1px solid ${T.borderBright}`,
                      color: T.textMid,
                      padding: "7px 14px",
                      fontSize: 10,
                      letterSpacing: 2,
                      cursor: "pointer",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    ADD PROMOTION
                  </button>
                </div>

                <div style={{ background: T.surface, border: `1px solid ${T.border}`, padding: 20 }}>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 16 }}>
                    ACTIVE PROMOTIONS
                  </div>
                  {promotions.length === 0 ? (
                    <div style={{ fontSize: 11, color: T.textDim }}>No promotions yet</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      {promotions.map((promo, index) => (
                        <div key={`${promo.name}-${index}`} style={{
                          border: `1px solid ${T.borderBright}`,
                          padding: 12,
                          background: "#0d0d0d",
                        }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div>
                              <div style={{ fontSize: 12, color: T.text }}>{promo.name}</div>
                              <div style={{ fontSize: 10, color: T.textDim }}>{promo.url}</div>
                            </div>
                            <button
                              onClick={() => handleRemovePromotion(index)}
                              style={{
                                background: "transparent",
                                border: `1px solid ${T.borderBright}`,
                                color: T.textDim,
                                padding: "4px 8px",
                                fontSize: 9,
                                letterSpacing: 1,
                                cursor: "pointer",
                                fontFamily: "'JetBrains Mono', monospace",
                              }}
                            >
                              REMOVE
                            </button>
                          </div>
                          <div style={{ fontSize: 11, color: T.textMid, marginTop: 8, whiteSpace: "pre-wrap" }}>
                            {promo.context}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : activeTab === "settings" ? (
              <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
                {!config ? (
                  <div style={{ fontSize: 11, color: T.textDim }}>Loading settings...</div>
                ) : (
                  <>
                    <SettingsSection title="VOICE SETTINGS">
                      <SettingsInput
                        label="Niche"
                        value={config.voice?.niche}
                        onChange={(v) => updateConfig("voice", "niche", v)}
                      />
                      <SettingsInput
                        label="Product"
                        value={config.voice?.product}
                        onChange={(v) => updateConfig("voice", "product", v)}
                      />
                      <SettingsInput
                        label="Product URL"
                        value={config.voice?.product_url}
                        onChange={(v) => updateConfig("voice", "product_url", v)}
                      />
                      <SettingsInput
                        label="Personality"
                        value={config.voice?.personality}
                        onChange={(v) => updateConfig("voice", "personality", v)}
                      />
                      <SettingsTextarea
                        label="Never say (one per line)"
                        value={Array.isArray(config.voice?.never_say) ? config.voice.never_say.join("\n") : (config.voice?.never_say || "")}
                        onChange={(v) => updateConfig("voice", "never_say", v)}
                        placeholder="consistency is key"
                        rows={5}
                      />
                    </SettingsSection>

                    <SettingsSection title="POSTING">
                      <SettingsInput
                        label="Tweets per day"
                        type="number"
                        min="0"
                        value={config.posting?.tweets_per_day}
                        onChange={(v) => updateConfig("posting", "tweets_per_day", v)}
                      />
                      <SettingsInput
                        label="Tweet times (comma separated)"
                        value={Array.isArray(config.posting?.tweet_times) ? config.posting.tweet_times.join(", ") : (config.posting?.tweet_times || "")}
                        onChange={(v) => updateConfig("posting", "tweet_times", v)}
                        placeholder="09:30, 19:00"
                      />
                      <SettingsInput
                        label="Active hours start"
                        value={config.posting?.active_hours_start}
                        onChange={(v) => updateConfig("posting", "active_hours_start", v)}
                        placeholder="09:00"
                      />
                      <SettingsInput
                        label="Active hours end"
                        value={config.posting?.active_hours_end}
                        onChange={(v) => updateConfig("posting", "active_hours_end", v)}
                        placeholder="23:00"
                      />
                      <SettingsToggle
                        label="Require approval"
                        checked={config.posting?.require_approval}
                        onChange={(v) => updateConfig("posting", "require_approval", v)}
                      />
                      <SettingsToggle
                        label="Auto-generate tweets"
                        checked={config.posting?.auto_generate_tweets}
                        onChange={(v) => updateConfig("posting", "auto_generate_tweets", v)}
                      />
                      <SettingsToggle
                        label="Auto-generate threads"
                        checked={config.posting?.auto_generate_threads}
                        onChange={(v) => updateConfig("posting", "auto_generate_threads", v)}
                      />
                      <SettingsToggle
                        label="Auto-generate promos"
                        checked={config.posting?.auto_generate_promos}
                        onChange={(v) => updateConfig("posting", "auto_generate_promos", v)}
                      />
                    </SettingsSection>

                    <SettingsSection title="UI">
                      <SettingsToggle
                        label="Browser status overlay"
                        checked={config.ui?.status_overlay_enabled}
                        onChange={(v) => updateConfig("ui", "status_overlay_enabled", v)}
                      />
                    </SettingsSection>

                    <SettingsSection title="ENGAGEMENT LIMITS">
                      <SettingsInput label="Daily replies" type="number" min="0" value={config.engagement?.daily_replies} onChange={(v) => updateConfig("engagement", "daily_replies", v)} />
                      <SettingsInput label="Daily follows" type="number" min="0" value={config.engagement?.daily_follows} onChange={(v) => updateConfig("engagement", "daily_follows", v)} />
                      <SettingsInput label="Daily DMs" type="number" min="0" value={config.engagement?.daily_dms} onChange={(v) => updateConfig("engagement", "daily_dms", v)} />
                      <SettingsInput label="Daily likes" type="number" min="0" value={config.engagement?.daily_likes} onChange={(v) => updateConfig("engagement", "daily_likes", v)} />
                      <SettingsInput label="Daily retweets" type="number" min="0" value={config.engagement?.daily_retweets} onChange={(v) => updateConfig("engagement", "daily_retweets", v)} />
                      <SettingsInput label="Min delay (sec)" type="number" min="0" value={config.engagement?.min_delay_seconds} onChange={(v) => updateConfig("engagement", "min_delay_seconds", v)} />
                      <SettingsInput label="Max delay (sec)" type="number" min="0" value={config.engagement?.max_delay_seconds} onChange={(v) => updateConfig("engagement", "max_delay_seconds", v)} />
                    </SettingsSection>

                    <SettingsSection title="AUTONOMY MODE">
                      <SettingsToggle
                        label="Enable autonomy mode"
                        checked={config.autonomy_mode?.enabled}
                        onChange={(v) => updateConfig("autonomy_mode", "enabled", v)}
                      />
                      <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <span style={{ fontSize: 10, color: T.textDim, letterSpacing: 1 }}>
                          Autonomy level (0–100): {config.autonomy_mode?.level ?? 50}
                        </span>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="1"
                          value={config.autonomy_mode?.level ?? 50}
                          onChange={(e) => updateConfig("autonomy_mode", "level", e.target.value)}
                          style={{ width: "100%" }}
                        />
                      </label>
                    </SettingsSection>

                    <SettingsSection title="DYNAMIC LIMITS">
                      <SettingsToggle
                        label="Enable daily jitter"
                        checked={config.dynamic_limits?.enabled}
                        onChange={(v) => updateConfig("dynamic_limits", "enabled", v)}
                      />
                      <SettingsInput label="Daily jitter pct" type="number" step="0.05" min="0" value={config.dynamic_limits?.daily_jitter_pct} onChange={(v) => updateConfig("dynamic_limits", "daily_jitter_pct", v)} />
                      <SettingsInput label="Delay jitter pct" type="number" step="0.05" min="0" value={config.dynamic_limits?.delay_jitter_pct} onChange={(v) => updateConfig("dynamic_limits", "delay_jitter_pct", v)} />
                      <SettingsInput label="Hourly jitter pct" type="number" step="0.05" min="0" value={config.dynamic_limits?.hourly_jitter_pct} onChange={(v) => updateConfig("dynamic_limits", "hourly_jitter_pct", v)} />
                      <SettingsInput label="Session pause jitter pct" type="number" step="0.05" min="0" value={config.dynamic_limits?.session_pause_jitter_pct} onChange={(v) => updateConfig("dynamic_limits", "session_pause_jitter_pct", v)} />
                    </SettingsSection>

                    <SettingsSection title="TIERS">
                      {[
                        { key: "small", label: "0–1k" },
                        { key: "peer", label: "1k–10k" },
                        { key: "big", label: "10k+" },
                      ].map(tier => (
                        <div key={tier.key} style={{
                          border: `1px solid ${T.borderBright}`,
                          padding: 12,
                          background: "#0d0d0d",
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                          gap: 10,
                        }}>
                          <div style={{ gridColumn: "1 / -1", fontSize: 10, color: T.textMid, letterSpacing: 2 }}>
                            {tier.label}
                          </div>
                          <SettingsInput label="Min followers" type="number" min="0" value={config.tiers?.[tier.key]?.min_followers} onChange={(v) => updateConfigTier(tier.key, "min_followers", v)} />
                          <SettingsInput label="Max followers" type="number" min="0" value={config.tiers?.[tier.key]?.max_followers} onChange={(v) => updateConfigTier(tier.key, "max_followers", v)} />
                          <SettingsInput label="Behavior" value={config.tiers?.[tier.key]?.behavior} onChange={(v) => updateConfigTier(tier.key, "behavior", v)} />
                          <SettingsInput label="Comment tone" value={config.tiers?.[tier.key]?.comment_tone} onChange={(v) => updateConfigTier(tier.key, "comment_tone", v)} />
                          <SettingsToggle label="DM after engagement" checked={config.tiers?.[tier.key]?.dm_after_engagement} onChange={(v) => updateConfigTier(tier.key, "dm_after_engagement", v)} />
                          <SettingsInput label="DM delay min (min)" type="number" min="0" value={config.tiers?.[tier.key]?.dm_delay_min_minutes} onChange={(v) => updateConfigTier(tier.key, "dm_delay_min_minutes", v)} />
                          <SettingsInput label="DM delay max (min)" type="number" min="0" value={config.tiers?.[tier.key]?.dm_delay_max_minutes} onChange={(v) => updateConfigTier(tier.key, "dm_delay_max_minutes", v)} />
                        </div>
                      ))}
                    </SettingsSection>

                    <SettingsSection title="TARGET AUTO-ADD">
                      <SettingsToggle
                        label="Auto-add enabled"
                        checked={config.targets?.auto_add_enabled}
                        onChange={(v) => updateConfig("targets", "auto_add_enabled", v)}
                      />
                      <SettingsInput label="Auto-add max per day" type="number" min="0" value={config.targets?.auto_add_max_per_day} onChange={(v) => updateConfig("targets", "auto_add_max_per_day", v)} />
                      <SettingsInput label="Auto-add min followers" type="number" min="0" value={config.targets?.auto_add_min_followers} onChange={(v) => updateConfig("targets", "auto_add_min_followers", v)} />
                      <SettingsToggle
                        label="Follow from mentions"
                        checked={config.targets?.follow_from_mentions_enabled}
                        onChange={(v) => updateConfig("targets", "follow_from_mentions_enabled", v)}
                      />
                      <SettingsInput label="Mentions follows per session" type="number" min="0" value={config.targets?.follow_from_mentions_max_per_session} onChange={(v) => updateConfig("targets", "follow_from_mentions_max_per_session", v)} />
                      <SettingsToggle
                        label="Prefer small targets for follows"
                        checked={config.targets?.follow_from_small_targets_only}
                        onChange={(v) => updateConfig("targets", "follow_from_small_targets_only", v)}
                      />
                      <SettingsToggle
                        label="Follow from home feed"
                        checked={config.targets?.follow_from_home_enabled}
                        onChange={(v) => updateConfig("targets", "follow_from_home_enabled", v)}
                      />
                      <SettingsInput label="Home follows per session" type="number" min="0" value={config.targets?.follow_from_home_max_per_session} onChange={(v) => updateConfig("targets", "follow_from_home_max_per_session", v)} />
                    </SettingsSection>

                    <SettingsSection title="CONTENT TOPICS">
                      <SettingsTextarea
                        label="Topics (one per line)"
                        value={Array.isArray(config.content_topics) ? config.content_topics.join("\n") : (config.content_topics || "")}
                        onChange={(v) => updateConfigRoot("content_topics", v)}
                        placeholder="building in public"
                        rows={6}
                      />
                    </SettingsSection>

                    <SettingsSection title="VOICE DIRECTION">
                      <SettingsTextarea
                        label="Voice pillars (one per line)"
                        value={Array.isArray(config.content_strategy?.voice_pillars) ? config.content_strategy.voice_pillars.join("\n") : (config.content_strategy?.voice_pillars || "")}
                        onChange={(v) => updateConfig("content_strategy", "voice_pillars", v)}
                        placeholder="product mechanics"
                        rows={5}
                      />
                      <SettingsTextarea
                        label="Proof bank (one per line)"
                        value={Array.isArray(config.content_strategy?.proof_bank) ? config.content_strategy.proof_bank.join("\n") : (config.content_strategy?.proof_bank || "")}
                        onChange={(v) => updateConfig("content_strategy", "proof_bank", v)}
                        placeholder="Dropped onboarding from 7 steps to 3 and activation rose 18% in 2 weeks."
                        rows={6}
                      />
                      <SettingsTextarea
                        label="Signature angles (one per line)"
                        value={Array.isArray(config.content_strategy?.signature_angles) ? config.content_strategy.signature_angles.join("\n") : (config.content_strategy?.signature_angles || "")}
                        onChange={(v) => updateConfig("content_strategy", "signature_angles", v)}
                        placeholder="tradeoffs beat hacks"
                        rows={5}
                      />
                      <SettingsTextarea
                        label="Weekly direction (one per line)"
                        value={Array.isArray(config.content_strategy?.weekly_direction) ? config.content_strategy.weekly_direction.join("\n") : (config.content_strategy?.weekly_direction || "")}
                        onChange={(v) => updateConfig("content_strategy", "weekly_direction", v)}
                        placeholder="testing a new activation email sequence"
                        rows={5}
                      />
                      <SettingsToggle
                        label="Tweet templates enabled"
                        checked={config.content_strategy?.tweet_templates_enabled}
                        onChange={(v) => updateConfig("content_strategy", "tweet_templates_enabled", v)}
                      />
                      <SettingsToggle
                        label="Thread templates enabled"
                        checked={config.content_strategy?.thread_templates_enabled}
                        onChange={(v) => updateConfig("content_strategy", "thread_templates_enabled", v)}
                      />
                      <SettingsToggle
                        label="Require proof point"
                        checked={config.content_strategy?.require_proof}
                        onChange={(v) => updateConfig("content_strategy", "require_proof", v)}
                      />
                      <SettingsToggle
                        label="Require specificity"
                        checked={config.content_strategy?.require_specificity}
                        onChange={(v) => updateConfig("content_strategy", "require_specificity", v)}
                      />
                      <SettingsToggle
                        label="No questions unless explicit"
                        checked={config.content_strategy?.enforce_no_question}
                        onChange={(v) => updateConfig("content_strategy", "enforce_no_question", v)}
                      />
                      <SettingsToggle
                        label="Enforce uniqueness"
                        checked={config.content_strategy?.enforce_uniqueness}
                        onChange={(v) => updateConfig("content_strategy", "enforce_uniqueness", v)}
                      />
                      <SettingsInput
                        label="Uniqueness window (posts)"
                        type="number"
                        min="0"
                        value={config.content_strategy?.uniqueness_window}
                        onChange={(v) => updateConfig("content_strategy", "uniqueness_window", v)}
                      />
                      <SettingsInput
                        label="Uniqueness similarity threshold"
                        type="number"
                        step="0.05"
                        min="0"
                        value={config.content_strategy?.uniqueness_similarity_threshold}
                        onChange={(v) => updateConfig("content_strategy", "uniqueness_similarity_threshold", v)}
                      />
                      <SettingsInput
                        label="Max generation attempts"
                        type="number"
                        min="1"
                        value={config.content_strategy?.max_generation_attempts}
                        onChange={(v) => updateConfig("content_strategy", "max_generation_attempts", v)}
                      />
                    </SettingsSection>

                    <SettingsSection title="MENTIONS">
                      <SettingsTextarea
                        label="Tool mentions (one per line: name:@handle or name|@handle|aliases)"
                        value={Array.isArray(config.mentions?.tools) ? config.mentions.tools.join("\n") : (config.mentions?.tools || "")}
                        onChange={(v) => updateConfig("mentions", "tools", v)}
                        placeholder="Figma:@figma"
                        rows={4}
                      />
                    </SettingsSection>

                    <SettingsSection title="DISCOVERY + RELEVANCE">
                      <SettingsInput label="Target profile sessions per day" type="number" min="0" value={config.discovery?.target_profile_sessions_per_day} onChange={(v) => updateConfig("discovery", "target_profile_sessions_per_day", v)} />
                      <SettingsToggle
                        label="Reply from hashtags"
                        checked={config.discovery?.reply_from_hashtags}
                        onChange={(v) => updateConfig("discovery", "reply_from_hashtags", v)}
                      />
                      <SettingsToggle
                        label="DM from hashtag replies"
                        checked={config.discovery?.dm_from_hashtags}
                        onChange={(v) => updateConfig("discovery", "dm_from_hashtags", v)}
                      />
                      <SettingsToggle
                        label="Reply from home feed"
                        checked={config.discovery?.reply_from_home_feed}
                        onChange={(v) => updateConfig("discovery", "reply_from_home_feed", v)}
                      />
                      <SettingsToggle
                        label="DM from home replies"
                        checked={config.discovery?.dm_from_home_feed}
                        onChange={(v) => updateConfig("discovery", "dm_from_home_feed", v)}
                      />
                      <SettingsInput label="Hashtag replies per session" type="number" min="0" value={config.discovery?.max_hashtag_replies_per_session} onChange={(v) => updateConfig("discovery", "max_hashtag_replies_per_session", v)} />
                      <SettingsInput label="Home replies per session" type="number" min="0" value={config.discovery?.max_home_replies_per_session} onChange={(v) => updateConfig("discovery", "max_home_replies_per_session", v)} />
                      <SettingsInput label="Hashtag tweets scanned" type="number" min="0" value={config.discovery?.max_hashtag_tweets_scanned} onChange={(v) => updateConfig("discovery", "max_hashtag_tweets_scanned", v)} />
                      <SettingsInput label="Hashtag top ratio (0-1)" type="number" step="0.05" min="0" value={config.discovery?.hashtag_top_ratio} onChange={(v) => updateConfig("discovery", "hashtag_top_ratio", v)} />
                      <SettingsInput label="Home tweets scanned" type="number" min="0" value={config.discovery?.max_home_tweets_scanned} onChange={(v) => updateConfig("discovery", "max_home_tweets_scanned", v)} />
                      <SettingsToggle
                        label="Like from profiles (home feed)"
                        checked={config.discovery?.profile_like_from_home_enabled}
                        onChange={(v) => updateConfig("discovery", "profile_like_from_home_enabled", v)}
                      />
                      <SettingsInput label="Profile likes per session" type="number" min="0" value={config.discovery?.profile_like_profiles_per_session} onChange={(v) => updateConfig("discovery", "profile_like_profiles_per_session", v)} />
                      <SettingsInput label="Profile like min posts" type="number" min="0" value={config.discovery?.profile_like_min_posts} onChange={(v) => updateConfig("discovery", "profile_like_min_posts", v)} />
                      <SettingsInput label="Profile like max posts" type="number" min="0" value={config.discovery?.profile_like_max_posts} onChange={(v) => updateConfig("discovery", "profile_like_max_posts", v)} />
                      <SettingsInput label="Candidate score threshold" type="number" step="0.01" value={config.discovery?.candidate_score_threshold} onChange={(v) => updateConfig("discovery", "candidate_score_threshold", v)} />
                      <SettingsInput label="Min candidate words" type="number" min="0" value={config.discovery?.candidate_min_words} onChange={(v) => updateConfig("discovery", "candidate_min_words", v)} />
                      <SettingsInput label="Min unique word ratio" type="number" step="0.01" value={config.discovery?.candidate_min_unique_ratio} onChange={(v) => updateConfig("discovery", "candidate_min_unique_ratio", v)} />
                      <SettingsInput label="Thread topic min ratio" type="number" step="0.01" value={config.discovery?.thread_topic_min_ratio} onChange={(v) => updateConfig("discovery", "thread_topic_min_ratio", v)} />
                      <SettingsInput label="Thread quality min score" type="number" step="0.01" value={config.discovery?.thread_quality_min_score} onChange={(v) => updateConfig("discovery", "thread_quality_min_score", v)} />
                      <SettingsToggle
                        label="Use embeddings"
                        checked={config.discovery?.use_embeddings}
                        onChange={(v) => updateConfig("discovery", "use_embeddings", v)}
                      />
                      <SettingsInput label="Embedding threshold" type="number" step="0.01" value={config.discovery?.embedding_threshold} onChange={(v) => updateConfig("discovery", "embedding_threshold", v)} />
                      <SettingsToggle
                        label="Require keyword match"
                        checked={config.discovery?.require_keyword_match}
                        onChange={(v) => updateConfig("discovery", "require_keyword_match", v)}
                      />
                      <SettingsInput label="Min likes" type="number" min="0" value={config.discovery?.min_likes} onChange={(v) => updateConfig("discovery", "min_likes", v)} />
                      <SettingsInput label="Min replies" type="number" min="0" value={config.discovery?.min_replies} onChange={(v) => updateConfig("discovery", "min_replies", v)} />
                      <SettingsInput label="Min retweets" type="number" min="0" value={config.discovery?.min_retweets} onChange={(v) => updateConfig("discovery", "min_retweets", v)} />
                      <SettingsInput label="Min total engagement" type="number" min="0" value={config.discovery?.min_total_engagement} onChange={(v) => updateConfig("discovery", "min_total_engagement", v)} />
                      <SettingsInput label="Repeat topic window (hours)" type="number" min="0" value={config.discovery?.repeat_topic_window_hours} onChange={(v) => updateConfig("discovery", "repeat_topic_window_hours", v)} />
                      <SettingsInput label="Max topic repeats" type="number" min="0" value={config.discovery?.max_topic_repeats} onChange={(v) => updateConfig("discovery", "max_topic_repeats", v)} />
                      <SettingsTextarea
                        label="Relevance keywords (one per line)"
                        value={Array.isArray(config.discovery?.relevance_keywords) ? config.discovery.relevance_keywords.join("\n") : (config.discovery?.relevance_keywords || "")}
                        onChange={(v) => updateConfig("discovery", "relevance_keywords", v)}
                        placeholder="b2b"
                        rows={4}
                      />
                      <SettingsTextarea
                        label="Skip bait phrases (one per line)"
                        value={Array.isArray(config.discovery?.skip_bait_phrases) ? config.discovery.skip_bait_phrases.join("\n") : (config.discovery?.skip_bait_phrases || "")}
                        onChange={(v) => updateConfig("discovery", "skip_bait_phrases", v)}
                        placeholder="giveaway"
                        rows={5}
                      />
                    </SettingsSection>

                    <SettingsSection title="NOTIFICATIONS">
                      <SettingsToggle
                        label="Reply to mentions"
                        checked={config.notifications?.reply_to_mentions}
                        onChange={(v) => updateConfig("notifications", "reply_to_mentions", v)}
                      />
                      <SettingsInput label="Mention replies per session" type="number" min="0" value={config.notifications?.max_reply_notifications_per_session} onChange={(v) => updateConfig("notifications", "max_reply_notifications_per_session", v)} />
                      <SettingsToggle
                        label="Welcome new followers"
                        checked={config.notifications?.follow_welcome_enabled}
                        onChange={(v) => updateConfig("notifications", "follow_welcome_enabled", v)}
                      />
                      <SettingsInput label="Welcome DMs per session" type="number" min="0" value={config.notifications?.max_follow_welcomes_per_session} onChange={(v) => updateConfig("notifications", "max_follow_welcomes_per_session", v)} />
                      <SettingsInput label="Welcome like min posts" type="number" min="0" value={config.notifications?.follow_welcome_like_min_posts} onChange={(v) => updateConfig("notifications", "follow_welcome_like_min_posts", v)} />
                      <SettingsInput label="Welcome like max posts" type="number" min="0" value={config.notifications?.follow_welcome_like_max_posts} onChange={(v) => updateConfig("notifications", "follow_welcome_like_max_posts", v)} />
                    </SettingsSection>

                    <SettingsSection title="PROMOTIONS">
                      <SettingsInput label="Mentions per day" type="number" min="0" value={config.promotions?.mentions_per_day} onChange={(v) => updateConfig("promotions", "mentions_per_day", v)} />
                    </SettingsSection>

                    <SettingsSection title="VISION">
                      <SettingsToggle
                        label="Vision enabled"
                        checked={config.vision?.enabled}
                        onChange={(v) => updateConfig("vision", "enabled", v)}
                      />
                      <SettingsInput label="Vision model" value={config.vision?.model} onChange={(v) => updateConfig("vision", "model", v)} />
                      <SettingsInput label="Max images per tweet" type="number" min="0" value={config.vision?.max_images_per_tweet} onChange={(v) => updateConfig("vision", "max_images_per_tweet", v)} />
                      <SettingsInput label="Max image bytes" type="number" min="0" value={config.vision?.max_image_bytes} onChange={(v) => updateConfig("vision", "max_image_bytes", v)} />
                    </SettingsSection>

                    <SettingsSection title="SAFETY + PACING">
                      <SettingsInput label="Max actions per hour" type="number" min="0" value={config.safety?.max_actions_per_hour} onChange={(v) => updateConfig("safety", "max_actions_per_hour", v)} />
                      <SettingsInput label="Nav-heavy actions per session" type="number" min="0" value={config.safety?.nav_actions_per_session} onChange={(v) => updateConfig("safety", "nav_actions_per_session", v)} />
                      <SettingsInput label="Pause between sessions (min)" type="number" min="0" value={config.safety?.pause_between_sessions_minutes} onChange={(v) => updateConfig("safety", "pause_between_sessions_minutes", v)} />
                      <SettingsToggle
                        label="Idle scroll during waits"
                        checked={config.safety?.idle_scroll_enabled}
                        onChange={(v) => updateConfig("safety", "idle_scroll_enabled", v)}
                      />
                      <SettingsInput label="Idle scroll interval (min)" type="number" min="1" value={config.safety?.idle_scroll_interval_minutes} onChange={(v) => updateConfig("safety", "idle_scroll_interval_minutes", v)} />
                      <SettingsInput label="Idle scroll scrolls" type="number" min="1" value={config.safety?.idle_scroll_scrolls} onChange={(v) => updateConfig("safety", "idle_scroll_scrolls", v)} />
                      <SettingsInput label="Rate limit cooldown (min)" type="number" min="0" value={config.safety?.rate_limit_cooldown_minutes} onChange={(v) => updateConfig("safety", "rate_limit_cooldown_minutes", v)} />
                      <SettingsToggle
                        label="Dynamic pacing"
                        checked={config.safety?.dynamic_pacing}
                        onChange={(v) => updateConfig("safety", "dynamic_pacing", v)}
                      />
                      <SettingsInput label="Pacing multiplier max" type="number" step="0.1" min="1" value={config.safety?.pacing_multiplier_max} onChange={(v) => updateConfig("safety", "pacing_multiplier_max", v)} />
                      <SettingsToggle
                        label="Stop on rate limit"
                        checked={config.safety?.stop_on_rate_limit}
                        onChange={(v) => updateConfig("safety", "stop_on_rate_limit", v)}
                      />
                      <SettingsToggle
                        label="Never DM verified accounts"
                        checked={config.safety?.never_dm_verified_accounts}
                        onChange={(v) => updateConfig("safety", "never_dm_verified_accounts", v)}
                      />
                      <SettingsInput label="Unfollow non-followers after (days)" type="number" min="0" value={config.safety?.unfollow_non_followers_after_days} onChange={(v) => updateConfig("safety", "unfollow_non_followers_after_days", v)} />
                    </SettingsSection>

                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <button
                        onClick={handleSaveConfig}
                        disabled={configSaving}
                        style={{
                          background: configSaved ? T.accentMid : "transparent",
                          border: `1px solid ${configSaved ? T.accent : T.borderBright}`,
                          color: configSaved ? T.accent : T.textMid,
                          padding: "8px 18px",
                          fontSize: 10,
                          letterSpacing: 2,
                          cursor: configSaving ? "not-allowed" : "pointer",
                          fontFamily: "'JetBrains Mono', monospace",
                        }}
                      >
                        {configSaving ? "SAVING..." : configSaved ? "✓ SAVED" : "SAVE SETTINGS"}
                      </button>
                      {configError && (
                        <span style={{ fontSize: 11, color: T.red }}>{configError}</span>
                      )}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                {queue.length === 0 ? (
                  <div style={{
                    padding: "60px 20px",
                    textAlign: "center",
                    color: T.textDim,
                    fontSize: 12,
                    lineHeight: 2,
                  }}>
                    No tweets pending approval<br />
                    <span style={{ color: T.textDim, fontSize: 10 }}>
                      Agent will generate tweets based on your schedule
                    </span>
                  </div>
                ) : (
                  groupedQueue.map(group => (
                    <ThreadGroup
                      key={group.id}
                      group={group}
                      onApprove={handleApprove}
                      onSkip={handleSkip}
                      onRegenerate={handleRegenerate}
                      onAddNext={handleAddThreadNext}
                      onMediaUpload={handleMediaUpload}
                      onMediaRemove={handleMediaRemove}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right — Growth */}
        <div style={{
          width: 360,
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}>
          {/* Growth Chart */}
          <div style={{
            padding: 20,
            borderBottom: `1px solid ${T.border}`,
          }}>
            <div style={{
              fontSize: 10,
              letterSpacing: 3,
              color: T.textMid,
              marginBottom: 16,
            }}>FOLLOWER GROWTH</div>
            <GrowthChart data={growth} />
          </div>

          {/* Tier legend */}
          <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 12 }}>
              ENGAGEMENT TIERS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { tier: "small", label: "0–1k  RELATIONSHIP", desc: "Comments + DM conversations" },
                { tier: "peer", label: "1k–10k  NETWORKING", desc: "Peer engagement, mutual growth" },
                { tier: "big", label: "10k+  VISIBILITY", desc: "Early replies for reach" },
              ].map(({ tier, label, desc }) => (
                <div key={tier} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <div style={{
                    width: 3,
                    height: 36,
                    background: TIER_COLORS[tier],
                    flexShrink: 0,
                    marginTop: 2,
                  }} />
                  <div>
                    <div style={{ fontSize: 10, color: TIER_COLORS[tier], letterSpacing: 1 }}>{label}</div>
                    <div style={{ fontSize: 10, color: T.textDim, marginTop: 2 }}>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Target accounts */}
          <div style={{ padding: "16px 20px", flex: 1, overflowY: "auto" }}>
            <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 12 }}>
              WATCHING
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {[
                "levelsio", "marc_louvion", "arvidkahl", "gregisenberg",
                "thedankoe", "steveschoger", "brianlovin", "thepatwalls",
                "heyblake", "dannypostmaa", "tdinh_me", "venturetwins",
              ].map(account => (
                <span
                  key={account}
                  style={{
                    fontSize: 10,
                    color: T.textMid,
                    border: `1px solid ${T.border}`,
                    padding: "3px 8px",
                    cursor: "default",
                  }}
                >
                  @{account}
                </span>
              ))}
            </div>

            {/* Trends */}
            {trends.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <div style={{ fontSize: 10, letterSpacing: 3, color: T.textMid, marginBottom: 12 }}>
                  TODAY'S TRENDS
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {trends.slice(0, 8).map((trend, i) => (
                    <div key={i} style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "5px 0",
                      borderBottom: `1px solid ${T.border}`,
                    }}>
                      <span style={{ fontSize: 9, color: T.textDim, minWidth: 16 }}>{i + 1}</span>
                      <span style={{ fontSize: 11, color: T.text }}>{trend}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
