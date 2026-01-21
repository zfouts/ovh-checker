-- Seed datacenter display names
-- These are the actual datacenter codes used by OVH API (lowercase)
-- Includes both US and FR (Global) subsidiaries

-- ============================================================================
-- US Subsidiary Datacenters
-- ============================================================================
INSERT INTO datacenter_locations (datacenter_code, subsidiary, display_name, city, country, country_code, flag, region) VALUES
    -- Main US datacenters
    ('us-east-vin', 'US', 'Virginia', 'Vint Hill', 'United States', 'US', '🇺🇸', 'US'),
    ('us-west-hil', 'US', 'Oregon', 'Hillsboro', 'United States', 'US', '🇺🇸', 'US'),
    -- US Local Zones
    ('us-east-lz-atl', 'US', 'Atlanta', 'Atlanta', 'United States', 'US', '🇺🇸', 'US'),
    ('us-east-lz-dal', 'US', 'Dallas', 'Dallas', 'United States', 'US', '🇺🇸', 'US'),
    ('us-east-lz-mia', 'US', 'Miami', 'Miami', 'United States', 'US', '🇺🇸', 'US'),
    ('us-east-lz-nyc', 'US', 'New York', 'New York', 'United States', 'US', '🇺🇸', 'US'),
    ('us-west-lz-den', 'US', 'Denver', 'Denver', 'United States', 'US', '🇺🇸', 'US'),
    ('us-west-lz-lax', 'US', 'Los Angeles', 'Los Angeles', 'United States', 'US', '🇺🇸', 'US'),
    ('us-west-lz-pao', 'US', 'Palo Alto', 'Palo Alto', 'United States', 'US', '🇺🇸', 'US'),
    ('us-west-lz-sea', 'US', 'Seattle', 'Seattle', 'United States', 'US', '🇺🇸', 'US'),
    -- Canada
    ('ca-east-bhs', 'US', 'Beauharnois', 'Beauharnois', 'Canada', 'CA', '🇨🇦', 'CA'),
    -- Europe main
    ('eu-west-gra', 'US', 'Gravelines', 'Gravelines', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-sbg', 'US', 'Strasbourg', 'Strasbourg', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-lim', 'US', 'Frankfurt', 'Frankfurt', 'Germany', 'DE', '🇩🇪', 'EU'),
    ('eu-west-eri', 'US', 'London', 'London', 'United Kingdom', 'GB', '🇬🇧', 'EU'),
    ('eu-central-waw', 'US', 'Warsaw', 'Warsaw', 'Poland', 'PL', '🇵🇱', 'EU'),
    ('eu-south-mil', 'US', 'Milan', 'Milan', 'Italy', 'IT', '🇮🇹', 'EU'),
    -- Europe Local Zones
    ('eu-west-lz-ams', 'US', 'Amsterdam', 'Amsterdam', 'Netherlands', 'NL', '🇳🇱', 'EU'),
    ('eu-west-lz-bru', 'US', 'Brussels', 'Brussels', 'Belgium', 'BE', '🇧🇪', 'EU'),
    ('eu-west-lz-vie', 'US', 'Vienna', 'Vienna', 'Austria', 'AT', '🇦🇹', 'EU'),
    ('eu-west-lz-mrs', 'US', 'Marseille', 'Marseille', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-lz-zrh', 'US', 'Zurich', 'Zurich', 'Switzerland', 'CH', '🇨🇭', 'EU'),
    ('eu-central-lz-prg', 'US', 'Prague', 'Prague', 'Czech Republic', 'CZ', '🇨🇿', 'EU'),
    ('eu-south-lz-mad', 'US', 'Madrid', 'Madrid', 'Spain', 'ES', '🇪🇸', 'EU'),
    -- Asia Pacific
    ('ap-south-mum', 'US', 'Mumbai', 'Mumbai', 'India', 'IN', '🇮🇳', 'APAC'),
    ('ap-southeast-sgp', 'US', 'Singapore', 'Singapore', 'Singapore', 'SG', '🇸🇬', 'APAC'),
    ('ap-southeast-syd', 'US', 'Sydney', 'Sydney', 'Australia', 'AU', '🇦🇺', 'APAC')
ON CONFLICT (datacenter_code, subsidiary) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    city = EXCLUDED.city,
    country = EXCLUDED.country,
    country_code = EXCLUDED.country_code,
    flag = EXCLUDED.flag,
    region = EXCLUDED.region;

-- ============================================================================
-- FR (Global) Subsidiary Datacenters
-- ============================================================================
INSERT INTO datacenter_locations (datacenter_code, subsidiary, display_name, city, country, country_code, flag, region) VALUES
    -- Canada
    ('ca-east-bhs', 'FR', 'Beauharnois', 'Beauharnois', 'Canada', 'CA', '🇨🇦', 'CA'),
    -- Europe main
    ('eu-west-gra', 'FR', 'Gravelines', 'Gravelines', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-sbg', 'FR', 'Strasbourg', 'Strasbourg', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-lim', 'FR', 'Frankfurt', 'Frankfurt', 'Germany', 'DE', '🇩🇪', 'EU'),
    ('eu-west-eri', 'FR', 'London', 'London', 'United Kingdom', 'GB', '🇬🇧', 'EU'),
    ('eu-central-waw', 'FR', 'Warsaw', 'Warsaw', 'Poland', 'PL', '🇵🇱', 'EU'),
    ('eu-south-mil', 'FR', 'Milan', 'Milan', 'Italy', 'IT', '🇮🇹', 'EU'),
    -- Europe Local Zones
    ('eu-west-lz-ams', 'FR', 'Amsterdam', 'Amsterdam', 'Netherlands', 'NL', '🇳🇱', 'EU'),
    ('eu-west-lz-bru', 'FR', 'Brussels', 'Brussels', 'Belgium', 'BE', '🇧🇪', 'EU'),
    ('eu-west-lz-vie', 'FR', 'Vienna', 'Vienna', 'Austria', 'AT', '🇦🇹', 'EU'),
    ('eu-west-lz-mrs', 'FR', 'Marseille', 'Marseille', 'France', 'FR', '🇫🇷', 'EU'),
    ('eu-west-lz-zrh', 'FR', 'Zurich', 'Zurich', 'Switzerland', 'CH', '🇨🇭', 'EU'),
    ('eu-central-lz-prg', 'FR', 'Prague', 'Prague', 'Czech Republic', 'CZ', '🇨🇿', 'EU'),
    ('eu-south-lz-mad', 'FR', 'Madrid', 'Madrid', 'Spain', 'ES', '🇪🇸', 'EU'),
    -- Asia Pacific
    ('ap-south-mum', 'FR', 'Mumbai', 'Mumbai', 'India', 'IN', '🇮🇳', 'APAC'),
    ('ap-southeast-sgp', 'FR', 'Singapore', 'Singapore', 'Singapore', 'SG', '🇸🇬', 'APAC'),
    ('ap-southeast-syd', 'FR', 'Sydney', 'Sydney', 'Australia', 'AU', '🇦🇺', 'APAC')
ON CONFLICT (datacenter_code, subsidiary) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    city = EXCLUDED.city,
    country = EXCLUDED.country,
    country_code = EXCLUDED.country_code,
    flag = EXCLUDED.flag,
    region = EXCLUDED.region;
