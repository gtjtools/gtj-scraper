/**
 * Operator Service
 * Handles all operator-related API calls
 */

import axios from 'axios';
import { env } from '../lib/env';
import { Operator, OperatorCreateInput, CharterOperator } from '../types/operator';

const API_BASE_URL = env.API_URL;

/**
 * Get all operators with pagination
 */
export const getOperators = async (skip: number = 0, limit: number = 100): Promise<Operator[]> => {
  try {
    const response = await axios.get<Operator[]>(
      `${API_BASE_URL}/operators`,
      { params: { skip, limit } }
    );
    return response.data;
  } catch (error) {
    console.error('Error fetching operators:', error);
    throw error;
  }
};

/**
 * Get a single operator by ID
 */
export const getOperator = async (operatorId: string): Promise<Operator> => {
  try {
    const response = await axios.get<Operator>(
      `${API_BASE_URL}/operators/${operatorId}`
    );
    return response.data;
  } catch (error) {
    console.error('Error fetching operator:', error);
    throw error;
  }
};

/**
 * Create a new operator
 */
export const createOperator = async (operator: OperatorCreateInput): Promise<Operator> => {
  try {
    const response = await axios.post<Operator>(
      `${API_BASE_URL}/operators`,
      operator
    );
    return response.data;
  } catch (error) {
    console.error('Error creating operator:', error);
    throw error;
  }
};

/**
 * Find operator by name or certificate
 */
export const findOperatorByName = async (name: string): Promise<Operator | null> => {
  try {
    const operators = await getOperators();
    const found = operators.find(op =>
      op.name.toLowerCase() === name.toLowerCase()
    );
    return found || null;
  } catch (error) {
    console.error('Error finding operator:', error);
    return null;
  }
};

/**
 * Get or create operator
 * Tries to find an existing operator, creates one if not found
 */
export const getOrCreateOperator = async (
  name: string,
  certificateDesignator?: string
): Promise<Operator> => {
  try {
    // Try to find existing operator
    const existing = await findOperatorByName(name);
    if (existing) {
      return existing;
    }

    // Create new operator if not found
    return await createOperator({
      name,
      certificate_designator: certificateDesignator,
    });
  } catch (error) {
    console.error('Error getting or creating operator:', error);
    throw error;
  }
};

/**
 * Load charter operators from the charter API
 */
export const loadCharterOperators = async (): Promise<CharterOperator[]> => {
  try {
    const response = await axios.get<{ data: CharterOperator[] }>(
      `${API_BASE_URL}/charter/operators`
    );
    return response.data.data || [];
  } catch (error) {
    console.error('Error loading charter operators:', error);
    throw error;
  }
};
