export function normalizeProfileList(profiles) {
  if (!Array.isArray(profiles)) return [];

  return profiles.map((profile) => {
    if (typeof profile === 'string') {
      return {
        value: profile,
        label: profile,
        metadata: { filename: profile },
      };
    }

    const filename = profile?.filename?.replace(/\.json$/i, '') || '';
    const value = profile?.game || filename || 'profile';

    const labelParts = [];
    if (profile?.game) {
      labelParts.push(profile.game);
    } else if (filename) {
      labelParts.push(filename);
    } else {
      labelParts.push(value);
    }

    if (profile?.scope) {
      const scopeLabel = profile.scope === 'default' ? 'Default' : profile.scope;
      labelParts.push(scopeLabel);
    }

    if (Array.isArray(profile?.mapping_keys) && profile.mapping_keys.length > 0) {
      labelParts.push(`${profile.mapping_keys.length} keys`);
    }

    return {
      value,
      label: labelParts.join(' • '),
      metadata: profile,
    };
  });
}
