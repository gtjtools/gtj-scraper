interface TrustScoreGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export function TrustScoreGauge({ score, size = 'md' }: TrustScoreGaugeProps) {
  const sizeClasses = {
    sm: 'w-16 h-16',
    md: 'w-24 h-24',
    lg: 'w-32 h-32'
  };

  const textSizes = {
    sm: 'text-lg',
    md: 'text-2xl',
    lg: 'text-3xl'
  };

  const getColor = (score: number) => {
    if (score >= 90) return '#10b981'; // green
    if (score >= 75) return '#3b82f6'; // blue
    if (score >= 60) return '#f59e0b'; // amber
    return '#ef4444'; // red
  };

  const color = getColor(score);
  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className={`relative ${sizeClasses[size]}`}>
      <svg className="transform -rotate-90 size-full" viewBox="0 0 100 100">
        <circle
          cx="50"
          cy="50"
          r="45"
          stroke="#e5e7eb"
          strokeWidth="8"
          fill="none"
        />
        <circle
          cx="50"
          cy="50"
          r="45"
          stroke={color}
          strokeWidth="8"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center flex-col gap-0">
        <span className="text-sm font-semibold" style={{ color }}>{score}</span>
        <span className="text-[9px] text-muted-foreground leading-none">Trust</span>
      </div>
    </div>
  );
}
