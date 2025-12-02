import axios from 'axios';
import type { CharterOperator } from '../types/operator';

// Re-export CharterOperator type for backward compatibility
export type { CharterOperator } from '../types/operator';

const API_BASE_URL = '/api';

export interface TailSearchResult {
  found: boolean;
  tail_number?: string;
  operators?: Array<{
    operator_name: string;
    certificate_designator: string;
    charter_data: any;
    score: number;
  }>;
  aircraft?: Array<{
    registration: string;
    serial_number: string;
    make_model: string;
    operator: string;
    certificate_designator: string;
    faa_district: string;
  }>;
  message?: string;
}

export interface Part135Operator {
  'Part 135 Certificate Holder Name': string;
  'Certificate Designator': string;
  'Registration Number': string;
  'Serial Number': string;
  'Aircraft Make/Model/Series': string;
  'FAA Certificate Holding District Office': string;
}

// Search aircraft by tail number
export const searchByTailNumber = async (tailNumber: string): Promise<TailSearchResult> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/search/tail/${encodeURIComponent(tailNumber)}`);
    return response.data;
  } catch (error) {
    console.error('Error searching by tail number:', error);
    throw error;
  }
};

// Search charter operators
export const searchCharterOperators = async (query?: string): Promise<{ total: number; data: CharterOperator[] }> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/charter/operators`);

    if (query) {
      const filtered = response.data.data.filter((op: CharterOperator) =>
        op.company.toLowerCase().includes(query.toLowerCase()) ||
        op.locations.some(loc => loc.toLowerCase().includes(query.toLowerCase()))
      );
      return { total: filtered.length, data: filtered };
    }

    return response.data;
  } catch (error) {
    console.error('Error searching charter operators:', error);
    throw error;
  }
};

// Filter charter operators by certification
export const filterCharterOperators = async (filters: {
  cert?: string;
  minScore?: number;
}): Promise<{ total: number; data: CharterOperator[] }> => {
  try {
    const params = new URLSearchParams();
    if (filters.cert) params.append('cert', filters.cert);
    if (filters.minScore) params.append('minScore', filters.minScore.toString());

    const response = await axios.get(`${API_BASE_URL}/charter/filter?${params.toString()}`);
    return response.data;
  } catch (error) {
    console.error('Error filtering charter operators:', error);
    throw error;
  }
};

// Get operator details
export const getOperatorDetails = async (operatorName: string): Promise<any> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/charter/search/${encodeURIComponent(operatorName)}`);
    return response.data;
  } catch (error) {
    console.error('Error getting operator details:', error);
    throw error;
  }
};

// Search Part 135 operators
export const searchPart135Operators = async (query?: string): Promise<{ total: number; data: Part135Operator[] }> => {
  try {
    const url = query ? `${API_BASE_URL}/search?q=${encodeURIComponent(query)}` : `${API_BASE_URL}/operators`;
    const response = await axios.get(url);
    return response.data;
  } catch (error) {
    console.error('Error searching Part 135 operators:', error);
    throw error;
  }
};

// Search aircraft by airport location
export const searchAircraftByAirport = async (airport: string): Promise<Part135Operator[]> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/search?q=${encodeURIComponent(airport)}`);
    return response.data.data || [];
  } catch (error) {
    console.error('Error searching by airport:', error);
    throw error;
  }
};

// Search aircraft by operator
export const searchAircraftByOperator = async (operator: string): Promise<Part135Operator[]> => {
  try {
    const response = await axios.get(`${API_BASE_URL}/search?q=${encodeURIComponent(operator)}`);
    return response.data.data || [];
  } catch (error) {
    console.error('Error searching by operator:', error);
    throw error;
  }
};
