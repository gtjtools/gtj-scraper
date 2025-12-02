import {
  AlertCircle,
  Building2,
  Calculator,
  MapPin,
  Search,
  Shield,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { loadCharterOperators } from '../services/operator.service';
import { runFullScoringFlow } from '../services/scoring.service';
import { CharterOperator, ScoreResult } from '../types/operator';
import { ScoreResultModal } from './ScoreResultModal';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';

export function OperatorsPage() {
  const [operators, setOperators] = useState<CharterOperator[]>([]);
  const [filteredOperators, setFilteredOperators] = useState<CharterOperator[]>(
    []
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Score modal state
  const [showScoreModal, setShowScoreModal] = useState(false);
  const [scoreData, setScoreData] = useState<ScoreResult | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [scoringOperatorName, setScoringOperatorName] = useState<string>('');

  // Load operators on mount
  useEffect(() => {
    loadOperators();
  }, []);

  // Filter operators when search query changes
  useEffect(() => {
    filterOperators();
  }, [searchQuery, operators]);

  const loadOperators = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await loadCharterOperators();
      setOperators(data);
      setFilteredOperators(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load operators');
      toast.error('Failed to load operators');
    } finally {
      setIsLoading(false);
    }
  };

  const filterOperators = () => {
    if (!searchQuery.trim()) {
      setFilteredOperators(operators);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = operators.filter(
      (op) =>
        op.company.toLowerCase().includes(query) ||
        op.locations.some((loc) => loc.toLowerCase().includes(query)) ||
        op.part135_cert?.toLowerCase().includes(query)
    );
    setFilteredOperators(filtered);
  };

  const handleRunScore = async (operator: CharterOperator) => {
    try {
      setShowScoreModal(true);
      setScoreLoading(true);
      setScoreError(null);
      setScoreData(null);
      setScoringOperatorName(operator.company);

      toast.info(`Running full verification for ${operator.company}...`);

      // Ensure faa_state is available
      if (!operator.faa_state) {
        throw new Error('FAA state not available for this operator');
      }

      // Run the full scoring flow (NTSB + UCC)
      // faa_state is used as fallback if no UCC filings found in NTSB-based states
      const result = await runFullScoringFlow(operator.company, operator.faa_state);

      // Transform the full scoring result to match ScoreResult interface
      const scoreData = {
        operator_id: '', // Not returned by full flow
        operator_name: result.operator_name,
        ntsb_score: result.ntsb.score,
        total_incidents: result.ntsb.total_incidents,
        incidents: result.ntsb.incidents,
        calculated_at: result.verification_date,
        ucc_data: result.ucc, // Add UCC data
        live_view_url: result.ucc.live_view_url, // Add live view URL
      };

      setScoreData(scoreData as any);
      toast.success(`Full verification completed for ${operator.company}`);

      // Show live view URL if available
      if (result.ucc.live_view_url) {
        toast.info('UCC verification live view available in results', {
          duration: 5000,
        });
      }
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to run verification';
      setScoreError(errorMessage);
      toast.error(errorMessage);
      console.error('Full verification error:', err);
    } finally {
      setScoreLoading(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 150) return 'bg-green-600 text-white';
    if (score >= 100) return 'bg-yellow-600 text-white';
    return 'bg-orange-600 text-white';
  };

  const getCertBadges = (operator: CharterOperator): string[] => {
    const badges: string[] = [];
    const certs = operator.data?.certifications;

    if (certs?.argus_rating?.toLowerCase().includes('platinum')) {
      badges.push('ARGUS Platinum');
    } else if (certs?.argus_rating?.toLowerCase().includes('gold')) {
      badges.push('ARGUS Gold');
    }

    if (
      certs?.wyvern_certified &&
      certs.wyvern_certified !== 'No' &&
      certs.wyvern_certified !== 'N/A'
    ) {
      badges.push('Wyvern');
    }

    if (certs?.is_bao && certs.is_bao !== 'No' && certs.is_bao !== 'N/A') {
      badges.push('IS-BAO');
    }

    return badges;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Charter Operators Directory</h1>
          <p className="text-muted-foreground mt-1">
            Browse and score charter operators from the database
          </p>
        </div>
        <Button variant="outline" onClick={loadOperators} disabled={isLoading}>
          {isLoading ? 'Loading...' : 'Refresh'}
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search by company name, location, or Part 135 certificate..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Stats */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Building2 className="h-4 w-4" />
        <span>
          Showing {filteredOperators.length} of {operators.length} operators
        </span>
      </div>

      {/* Error State */}
      {error && (
        <Card className="p-6 bg-red-50 border-red-200">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-900">
                Error Loading Operators
              </h3>
              <p className="text-red-700 mt-1">{error}</p>
              <Button
                onClick={loadOperators}
                variant="outline"
                size="sm"
                className="mt-3"
              >
                Try Again
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="p-6 animate-pulse">
              <div className="h-6 bg-slate-200 rounded mb-3"></div>
              <div className="h-4 bg-slate-200 rounded mb-2 w-3/4"></div>
              <div className="h-4 bg-slate-200 rounded w-1/2"></div>
            </Card>
          ))}
        </div>
      )}

      {/* Operators Grid */}
      {!isLoading && !error && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredOperators.map((operator) => {
            const score = operator.score || 0;
            const certBadges = getCertBadges(operator);

            return (
              <Card
                key={operator.charter_operator_id || operator.company}
                className="p-6 hover:shadow-lg transition-shadow"
              >
                <div className="space-y-4">
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-semibold text-lg leading-tight mb-2">
                        {operator.company}
                      </h3>
                      {score > 0 && (
                        <Badge className={`${getScoreColor(score)} text-xs`}>
                          Score: {score}
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Part 135 Certificate */}
                  {operator.part135_cert && (
                    <div className="flex items-center gap-2 text-sm">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <span className="text-muted-foreground">
                        Part 135: {operator.part135_cert}
                      </span>
                    </div>
                  )}

                  {/* Locations */}
                  <div className="flex flex-wrap gap-2">
                    {operator.locations.map((location, idx) => (
                      <Badge key={idx} variant="secondary" className="text-xs">
                        <MapPin className="h-3 w-3 mr-1" />
                        {location}
                      </Badge>
                    ))}
                  </div>

                  {/* Certifications */}
                  {certBadges.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-2 border-t">
                      {certBadges.map((cert, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {cert}
                        </Badge>
                      ))}
                    </div>
                  )}

                  {/* Run Full Verification Button */}
                  <Button
                    onClick={() => handleRunScore(operator)}
                    className="w-full"
                    size="sm"
                  >
                    <Calculator className="h-4 w-4 mr-2" />
                    Run Full Verification
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredOperators.length === 0 && (
        <Card className="p-12 text-center">
          <Building2 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="font-semibold mb-2">No Operators Found</h3>
          <p className="text-muted-foreground">
            {searchQuery
              ? 'Try adjusting your search criteria'
              : 'No operators available in the database'}
          </p>
        </Card>
      )}

      {/* Score Result Modal */}
      <ScoreResultModal
        isOpen={showScoreModal}
        onClose={() => setShowScoreModal(false)}
        scoreData={scoreData}
        isLoading={scoreLoading}
        error={scoreError}
      />
    </div>
  );
}
