import { useState, useEffect } from 'react';
import { searchPart135Operators, searchCharterOperators } from '../services/api';

export interface TailNumberOption {
  tailNumber: string;
  operator: string;
  model: string;
}

export interface OperatorOption {
  id: string;
  name: string;
  locations: string[];
}

export function useTailNumbers() {
  const [tailNumbers, setTailNumbers] = useState<TailNumberOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTailNumbers = async () => {
      try {
        setLoading(true);
        const result = await searchPart135Operators();

        // Convert Part 135 data to tail number options
        const uniqueTails = new Map<string, TailNumberOption>();

        result.data.forEach((op) => {
          const tailNum = op['Registration Number'];
          if (tailNum) {
            // Convert to string and trim
            const tailNumStr = String(tailNum).trim();
            if (tailNumStr !== '') {
              uniqueTails.set(tailNumStr, {
                tailNumber: tailNumStr,
                operator: op['Part 135 Certificate Holder Name'] || 'Unknown',
                model: op['Aircraft Make/Model/Series'] || 'Unknown',
              });
            }
          }
        });

        setTailNumbers(Array.from(uniqueTails.values()));
        setError(null);
      } catch (err) {
        console.error('Error fetching tail numbers:', err);
        setError('Failed to load tail numbers');
      } finally {
        setLoading(false);
      }
    };

    fetchTailNumbers();
  }, []);

  return { tailNumbers, loading, error };
}

export function useOperators() {
  const [operators, setOperators] = useState<OperatorOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchOperators = async () => {
      try {
        setLoading(true);
        const result = await searchCharterOperators();

        // Convert charter operator data to operator options
        const operatorOptions = result.data.map((op, index) => ({
          id: op.charter_operator_id || op.url || `op-${index}`,
          name: op.company,
          locations: op.locations || [],
        }));

        setOperators(operatorOptions);
        setError(null);
      } catch (err) {
        console.error('Error fetching operators:', err);
        setError('Failed to load operators');
      } finally {
        setLoading(false);
      }
    };

    fetchOperators();
  }, []);

  return { operators, loading, error };
}
