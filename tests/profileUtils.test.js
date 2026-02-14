import { normalizeProfileList } from '../frontend/src/panels/controller/utils/profileUtils.js';

describe('normalizeProfileList', () => {
  test('returns empty array for invalid input', () => {
    expect(normalizeProfileList(undefined)).toEqual([]);
    expect(normalizeProfileList(null)).toEqual([]);
  });

  test('normalizes string profiles', () => {
    const result = normalizeProfileList(['default.json']);
    expect(result).toEqual([
      {
        value: 'default.json',
        label: 'default.json',
        metadata: { filename: 'default.json' },
      },
    ]);
  });

  test('normalizes rich profile objects', () => {
    const result = normalizeProfileList([
      { filename: 'sf2.json', scope: 'game', game: 'Street Fighter II', mapping_keys: ['p1.button1'] },
      { filename: 'default.json', scope: 'default', mapping_keys: [] },
    ]);

    expect(result[0]).toMatchObject({
      value: 'Street Fighter II',
      label: 'Street Fighter II • game • 1 keys',
      metadata: {
        filename: 'sf2.json',
        scope: 'game',
        game: 'Street Fighter II',
        mapping_keys: ['p1.button1'],
      },
    });

    expect(result[1]).toMatchObject({
      value: 'default',
      label: 'default • Default',
    });
  });
});
