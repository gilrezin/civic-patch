import { absoluteTime, timeAgo, useNow } from "../utils/time";

/** Relative timestamp ("3 hours ago") that refreshes itself; hover shows the exact time. */
export function TimeAgo({ iso, className = "" }: { iso: string; className?: string }) {
  const now = useNow();
  return (
    <time dateTime={iso} title={absoluteTime(iso)} className={`timeago ${className}`.trim()}>
      {timeAgo(iso, now)}
    </time>
  );
}
