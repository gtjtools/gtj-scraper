/**
 * Scoring Service
 * Handles all scoring-related API calls including NTSB data fetching
 */

import axios from 'axios';
import { env } from '../lib/env';

const API_BASE_URL = env.API_URL;

// Type definitions matching backend schemas
export interface NTSBIncident {
  event_id?: string | null;
  event_date?: string | null;
  location?: string | null;
  aircraft_damage?: string | null;
  injury_level?: string | null;
  investigation_type?: string | null;
  event_type?: string | null;
}

export interface ScoreCalculationResponse {
  operator_id: string;
  operator_name: string;
  ntsb_score: number;
  total_incidents: number;
  incidents: NTSBIncident[];
  calculated_at: string;
}

export interface ScoringError {
  detail: string;
}

export interface UCCVerificationResult {
  status: string;
  live_view_url?: string;
  session_id?: string;
  error?: string;
}

export interface TrustScoreBreakdown {
  category: string;
  deduction: number;
  details?: string;
  reasoning?: string;
}

export interface TrustScoreResult {
  trust_score: number;
  fleet_score: number;
  tail_score: number;
  fleet_breakdown: {
    initial_score: number;
    final_score: number;
    total_deductions: number;
    deductions: TrustScoreBreakdown[];
  };
  tail_breakdown: {
    initial_score: number;
    final_score: number;
    total_deductions: number;
    deductions: TrustScoreBreakdown[];
  };
  calculated_at: string;
  llm_error?: string;
}

export interface FullScoringFlowResponse {
  operator_name: string;
  verification_date: string;
  ntsb: {
    score: number;
    total_incidents: number;
    incidents: NTSBIncident[];
    raw_response?: any;
  };
  ucc: UCCVerificationResult;
  trust_score?: TrustScoreResult;
  saved_file?: string;
  combined_score: number;
  status: string;
}

/**
 * Run score calculation for an operator
 * @param operatorId - UUID of the operator
 * @returns Score calculation result with NTSB data
 * @throws Error if the API request fails
 */
export const runScoreCalculation = async (
  operatorId: string
): Promise<ScoreCalculationResponse> => {
  try {
    const response = await axios.post<ScoreCalculationResponse>(
      `${API_BASE_URL}/scoring/run-score/${operatorId}`,
      {},
      {
        timeout: 60000, // 60 second timeout for NTSB API calls
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.code === 'ECONNABORTED') {
        throw new Error('Score calculation timed out. The NTSB API may be slow or unavailable. Please try again.');
      }
      const errorDetail = error.response?.data?.detail || error.message;
      console.error('Error running score calculation:', errorDetail);
      throw new Error(errorDetail);
    }
    console.error('Unexpected error running score calculation:', error);
    throw error;
  }
};

/**
 * Run full scoring flow (NTSB + UCC verification) for an operator
 * @param operatorName - Name of the operator
 * @param faaState - FAA state code (2-letter abbreviation) - used as fallback if no filings found
 * @param state - Optional state for UCC search override
 * @param sessionId - Optional existing Browserbase session ID
 * @returns Full scoring results with NTSB and UCC data
 * @throws Error if the API request fails
 */
export const runFullScoringFlow = async (
  operatorName: string,
  faaState: string,
  state?: string,
  sessionId?: string
): Promise<FullScoringFlowResponse> => {
  try {
    const params = new URLSearchParams();
    params.append('operator_name', operatorName);
    params.append('faa_state', faaState);
    if (state) params.append('state', state);
    if (sessionId) params.append('session_id', sessionId);

    const response = await axios.post<FullScoringFlowResponse>(
      `${API_BASE_URL}/scoring/full-scoring-flow?${params.toString()}`,
      {},
      {
        timeout: 120000, // 2 minute timeout for full verification (NTSB + UCC)
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.code === 'ECONNABORTED') {
        throw new Error('Full verification timed out. Please try again.');
      }
      const errorDetail = error.response?.data?.detail || error.message;
      console.error('Error running full scoring flow:', errorDetail);
      throw new Error(errorDetail);
    }
    console.error('Unexpected error running full scoring flow:', error);
    throw error;
  }
};

/**
 * Check scoring service health
 * @returns Health status of the scoring service
 */
export const checkScoringHealth = async (): Promise<{
  status: string;
  service: string;
  ntsb_api_url: string;
}> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/scoring/health`);
    return response.data;
  } catch (error) {
    console.error('Error checking scoring health:', error);
    throw error;
  }
};
