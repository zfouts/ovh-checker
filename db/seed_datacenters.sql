-- Seed datacenter display names
-- NOTE: With multi-subsidiary support, datacenter locations are now auto-discovered 
-- from each subsidiary's catalog. This seed file is optional and provides fallback data
-- for the default 'US' subsidiary.

INSERT INTO datacenter_locations (datacenter_code, subsidiary, display_name, city, country, country_code, flag, region) VALUES
    ('BHS', 'US', 'Beauharnois', 'Beauharnois', 'Canada', 'CA', '🇨🇦', 'CA'),
    ('GRA', 'US', 'Gravelines', 'Gravelines', 'France', 'FR', '🇫🇷', 'EU'),
    ('SBG', 'US', 'Strasbourg', 'Strasbourg', 'France', 'FR', '🇫🇷', 'EU'),
    ('DE', 'US', 'Frankfurt', 'Frankfurt', 'Germany', 'DE', '🇩🇪', 'EU'),
    ('UK', 'US', 'London', 'London', 'United Kingdom', 'GB', '🇬🇧', 'EU'),
    ('WAW', 'US', 'Warsaw', 'Warsaw', 'Poland', 'PL', '🇵🇱', 'EU'),
    ('YNM', 'US', 'Mumbai', 'Mumbai', 'India', 'IN', '🇮🇳', 'APAC'),
    ('EU-SOUTH-MIL', 'US', 'Milan', 'Milan', 'Italy', 'IT', '🇮🇹', 'EU'),
    ('US-EAST-VA', 'US', 'Virginia', 'Vint Hill', 'United States', 'US', '🇺🇸', 'US'),
    ('US-WEST-OR', 'US', 'Oregon', 'Hillsboro', 'United States', 'US', '🇺🇸', 'US'),
    ('EU-WEST-LZ-BRU', 'US', 'Brussels', 'Brussels', 'Belgium', 'BE', '🇧🇪', 'EU'),
    ('EU-WEST-LZ-AMS', 'US', 'Amsterdam', 'Amsterdam', 'Netherlands', 'NL', '🇳🇱', 'EU'),
    ('EU-WEST-LZ-VIE', 'US', 'Vienna', 'Vienna', 'Austria', 'AT', '🇦🇹', 'EU'),
    ('EU-WEST-LZ-MRS', 'US', 'Marseille', 'Marseille', 'France', 'FR', '🇫🇷', 'EU'),
    ('EU-WEST-LZ-ZRH', 'US', 'Zurich', 'Zurich', 'Switzerland', 'CH', '🇨🇭', 'EU'),
    ('EU-CENTRAL-LZ-PRG', 'US', 'Prague', 'Prague', 'Czech Republic', 'CZ', '🇨🇿', 'EU'),
    ('EU-SOUTH-LZ-MAD', 'US', 'Madrid', 'Madrid', 'Spain', 'ES', '🇪🇸', 'EU'),
    ('US-EAST-LZ-ATL', 'US', 'Atlanta', 'Atlanta', 'United States', 'US', '🇺🇸', 'US'),
    ('US-EAST-LZ-DAL', 'US', 'Dallas', 'Dallas', 'United States', 'US', '🇺🇸', 'US'),
    ('US-EAST-LZ-MIA', 'US', 'Miami', 'Miami', 'United States', 'US', '🇺🇸', 'US'),
    ('US-EAST-LZ-NYC', 'US', 'New York', 'New York', 'United States', 'US', '🇺🇸', 'US'),
    ('US-WEST-LZ-DEN', 'US', 'Denver', 'Denver', 'United States', 'US', '🇺🇸', 'US'),
    ('US-WEST-LZ-LAX', 'US', 'Los Angeles', 'Los Angeles', 'United States', 'US', '🇺🇸', 'US'),
    ('US-WEST-LZ-PAO', 'US', 'Palo Alto', 'Palo Alto', 'United States', 'US', '🇺🇸', 'US'),
    ('US-WEST-LZ-SEA', 'US', 'Seattle', 'Seattle', 'United States', 'US', '🇺🇸', 'US')
ON CONFLICT (datacenter_code, subsidiary) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    city = EXCLUDED.city,
    country = EXCLUDED.country,
    country_code = EXCLUDED.country_code,
    flag = EXCLUDED.flag,
    region = EXCLUDED.region;
