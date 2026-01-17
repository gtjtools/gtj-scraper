/**
 * Operator Types
 * TypeScript interfaces for operator-related data
 */

export interface OperatorCertifications {
  aoc_part135?: string;
  wyvern_certified?: string;
  argus_rating?: string;
  is_bao?: string;
  acsf_ias?: string;
}

export interface OperatorContact {
  telephone?: string;
  email?: string;
  website?: string;
}

export interface OperatorBase {
  location: string;
  aircraft: string;
  type?: string;
}

export interface OperatorData {
  certifications?: OperatorCertifications;
  contact?: OperatorContact;
  bases?: OperatorBase[];
  url?: string;
  country?: string;
  name?: string;
}

export interface CharterOperator {
  charter_operator_id?: string; // UUID from backend
  company: string;
  locations: string[];
  score?: number;
  part135_cert?: string;
  faa_state?: string; // 2-letter state code from FAA database
  faa_data?: any;
  data?: OperatorData;
  url?: string;
  created_at?: string; // ISO datetime string
  updated_at?: string; // ISO datetime string
}

export interface Operator {
  operator_id: string;
  name: string;
  certificate_designator?: string;
  created_at?: string;
  updated_at?: string;
}

export interface OperatorCreateInput {
  name: string;
  certificate_designator?: string;
}

export interface ScoreResult {
  operator_id: string;
  operator_name: string;
  ntsb_score: number;
  total_incidents: number;
  incidents: NTSBIncident[];
  calculated_at: string;
  live_view_url?: string;
  session_id?: string;
}

export interface NTSBIncident {
  event_id?: string | null;
  event_date?: string | null;
  location?: string | null;
  aircraft_damage?: string | null;
  injury_level?: string | null;
  investigation_type?: string | null;
  event_type?: string | null;
}
