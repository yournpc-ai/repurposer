import React, { type CSSProperties, type ReactNode } from "react";

export function DeviceFrame({
  variant,
  children,
  style,
}: {
  variant: "phone" | "laptop" | "browser" | "tablet";
  children: ReactNode;
  style?: CSSProperties;
}): React.JSX.Element {
  const compact = variant === "phone" || variant === "tablet";
  const radius = compact ? 46 : 24;
  return (
    <div
      style={{
        position: "relative",
        padding: compact ? 9 : 7,
        borderRadius: radius,
        boxSizing: "border-box",
        background:
          "linear-gradient(118deg,#f7f3ec 0%,#93928e 8%,#363939 28%,#d5d1ca 53%,#777873 78%,#c0c1bc)",
        borderTop: "1px solid #fff",
        boxShadow:
          "0 3px 5px #0008,0 22px 34px #07070752,0 66px 100px #12111450",
        ...style,
      }}
    >
      <div
        style={{
          height: "100%",
          borderRadius: radius - 7,
          overflow: "hidden",
          position: "relative",
          background: "#0e1012",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {variant === "browser" && (
          <div
            style={{
              height: 37,
              flexShrink: 0,
              background: "#dadcde",
              display: "flex",
              gap: 8,
              alignItems: "center",
              paddingLeft: 18,
            }}
          >
            {["#9c9d9f", "#a7a8aa", "#b6b7b8"].map((color) => (
              <i
                key={color}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: color,
                }}
              />
            ))}
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
        {variant === "phone" && (
          <i
            style={{
              position: "absolute",
              top: 12,
              left: "36%",
              width: "28%",
              height: 21,
              borderRadius: 18,
              background: "#090a0b",
            }}
          />
        )}
        <div
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background:
              "linear-gradient(119deg,#ffffff12,transparent 34%,transparent 64%,#ffffff08)",
          }}
        />
      </div>
      {variant === "laptop" && (
        <div
          style={{
            position: "absolute",
            bottom: -9,
            left: "-4%",
            width: "108%",
            height: 13,
            borderRadius: "3px 3px 65% 65%",
            background: "linear-gradient(#d9dbdb,#7d8082)",
          }}
        />
      )}
    </div>
  );
}
