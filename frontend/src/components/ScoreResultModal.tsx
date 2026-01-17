import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Separator } from './ui/separator';
import { ScoreResult } from '../types/operator';
import { AlertCircle, CheckCircle, Calendar, MapPin, AlertTriangle } from 'lucide-react';

interface ScoreResultModalProps {
  isOpen: boolean;
  onClose: () => void;
  scoreData: ScoreResult | null;
  isLoading?: boolean;
  error?: string | null;
}

export function ScoreResultModal({
  isOpen,
  onClose,
  scoreData,
  isLoading = false,
  error = null,
}: ScoreResultModalProps) {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getScoreBgGradient = (score: number) => {
    if (score >= 80) return 'from-green-500 to-emerald-600';
    if (score >= 60) return 'from-yellow-500 to-orange-600';
    return 'from-red-500 to-rose-600';
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader className="shrink-0">
          <DialogTitle>NTSB Score Calculation</DialogTitle>
          <DialogDescription>
            Safety score based on NTSB incident database
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-y-auto flex-1 -mx-6 px-6">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#335cff] mx-auto mb-4"></div>
                <p className="text-muted-foreground">Calculating score from NTSB database...</p>
                <p className="text-sm text-muted-foreground mt-2">This may take a moment</p>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-red-900">Error</h3>
                  <p className="text-red-700 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {!isLoading && !error && scoreData && (
            <div className="space-y-6">
              {/* Operator Name */}
              <div>
                <h3 className="text-2xl font-bold">{scoreData.operator_name}</h3>
                <p className="text-sm text-muted-foreground">
                  Calculated: {new Date(scoreData.calculated_at).toLocaleString()}
                </p>
              </div>

              {/* Browserbase Live View */}
              {scoreData.live_view_url && (
                <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl p-1">
                  <div className="bg-white rounded-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-3 text-white font-semibold flex items-center gap-2">
                      <span className="text-lg">🎥</span>
                      <span>Live Browser Session</span>
                      {scoreData.session_id && (
                        <span className="ml-auto text-xs text-blue-100">
                          Session: {scoreData.session_id.substring(0, 8)}...
                        </span>
                      )}
                    </div>
                    <div className="bg-white p-4">
                      <p className="text-sm text-muted-foreground mb-3">
                        Watch the live browser automation in action. This shows the real-time UCC verification process.
                      </p>
                      <iframe
                        src={scoreData.live_view_url}
                        className="w-full h-[400px] border-2 border-gray-200 rounded-lg"
                        sandbox="allow-same-origin allow-scripts"
                        allow="clipboard-read; clipboard-write"
                        title="Browserbase Live View"
                      />
                      <div className="mt-3 flex gap-2">
                        <a
                          href={scoreData.live_view_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          Open in new window →
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Score Display */}
              <div className={`bg-gradient-to-br ${getScoreBgGradient(scoreData.ntsb_score)} rounded-2xl p-8 text-white`}>
                <div className="text-center">
                  <p className="text-white/90 text-sm font-medium mb-2">NTSB SAFETY SCORE</p>
                  <p className="text-6xl font-bold mb-2">{scoreData.ntsb_score}</p>
                  <p className="text-white/90 text-sm">out of 100</p>
                </div>
              </div>

              {/* Summary Stats */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Total Incidents</p>
                  </div>
                  <p className="text-2xl font-bold">{scoreData.total_incidents}</p>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    {scoreData.total_incidents === 0 ? (
                      <CheckCircle className="h-4 w-4 text-green-600" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-yellow-600" />
                    )}
                    <p className="text-sm text-muted-foreground">Status</p>
                  </div>
                  <p className="text-lg font-semibold">
                    {scoreData.total_incidents === 0 ? 'Clean Record' : 'Incidents Found'}
                  </p>
                </div>
              </div>

              <Separator />

              {/* Incidents List */}
              {scoreData.incidents && scoreData.incidents.length > 0 ? (
                <div>
                  <h4 className="font-semibold mb-4">NTSB Incident Reports ({scoreData.total_incidents})</h4>
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {scoreData.incidents.map((incident, index) => {
                      const injuryLevel = incident.injury_level || 'Unknown';
                      const isFatal = injuryLevel.toLowerCase().includes('fatal');
                      const isSerious = injuryLevel.toLowerCase().includes('serious');
                      const isAccident = incident.event_type?.toLowerCase() === 'accident';

                      return (
                        <div
                          key={index}
                          className={`border-l-4 ${
                            isFatal ? 'border-red-500' : isSerious ? 'border-orange-500' : 'border-green-500'
                          } rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow`}
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1">
                              <p className="font-semibold text-lg">
                                {incident.event_id || `Incident #${index + 1}`}
                              </p>
                              {incident.event_type && (
                                <Badge
                                  variant={isAccident ? 'destructive' : 'secondary'}
                                  className="mt-1"
                                >
                                  {incident.event_type}
                                </Badge>
                              )}
                            </div>
                            {incident.injury_level && (
                              <div className="text-right">
                                <p className="text-xs text-muted-foreground">Injury Level</p>
                                <p className={`font-semibold ${
                                  isFatal ? 'text-red-600' : isSerious ? 'text-orange-600' : 'text-green-600'
                                }`}>
                                  {injuryLevel}
                                </p>
                              </div>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-3 text-sm">
                            {incident.event_date && (
                              <div>
                                <p className="text-xs text-muted-foreground mb-1">📅 Date</p>
                                <p className="font-medium">
                                  {new Date(incident.event_date).toLocaleDateString('en-US', {
                                    year: 'numeric',
                                    month: 'long',
                                    day: 'numeric'
                                  })}
                                </p>
                              </div>
                            )}
                            {incident.location && (
                              <div>
                                <p className="text-xs text-muted-foreground mb-1">📍 Location</p>
                                <p className="font-medium">{incident.location}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                  <div className="flex items-start gap-3">
                    <CheckCircle className="h-6 w-6 text-green-600 mt-0.5" />
                    <div>
                      <h3 className="font-semibold text-green-900">No NTSB Incidents Found</h3>
                      <p className="text-green-700 mt-1">
                        This operator has a clean safety record with no incidents reported in the NTSB database.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="shrink-0 pt-4 border-t">
          <Button onClick={onClose} className="w-full">
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
