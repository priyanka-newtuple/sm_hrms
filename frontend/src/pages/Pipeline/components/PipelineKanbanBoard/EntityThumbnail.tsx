interface EntityThumbnailProps {
  url: string;
}

export default function EntityThumbnail({ url }: EntityThumbnailProps) {
  return (
    <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-muted">
      <img src={url} alt="" className="h-full w-full object-cover" draggable={false} />
    </div>
  );
}
