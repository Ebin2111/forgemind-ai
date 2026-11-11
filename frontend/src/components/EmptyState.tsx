import Icon from "@/components/Icon";

/** Friendly placeholder when a list or panel has nothing to show. */
export default function EmptyState({
  icon, title, children,
}: {
  icon: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon d={icon} size={26} /></span>
      <p className="empty-title">{title}</p>
      {children && <div className="empty-text">{children}</div>}
    </div>
  );
}