"""Comparison endpoints for US vs Global pricing and availability."""
from typing import Optional, Dict, List, Any
from fastapi import APIRouter, Query

from db_instance import db
from services.currency import converter, calculate_price_difference

router = APIRouter(tags=["comparison"])


def calculate_cost_efficiency(plan_data: Dict, us_price: Optional[float], global_price_usd: Optional[float]) -> Optional[Dict]:
    """
    Calculate cost efficiency metrics for a plan.
    
    Returns $/vCPU, $/GB RAM, $/GB storage for both US and Global regions.
    """
    vcpu = plan_data.get('vcpu')
    ram_gb = plan_data.get('ram_gb')
    storage_gb = plan_data.get('storage_gb')
    
    if not vcpu or not ram_gb or not storage_gb:
        return None
    
    result = {
        'vcpu': vcpu,
        'ram_gb': ram_gb,
        'storage_gb': storage_gb,
        'us': None,
        'global': None,
        'best_for_cpu': None,
        'best_for_ram': None,
        'best_for_storage': None
    }
    
    if us_price and us_price > 0:
        result['us'] = {
            'price_per_vcpu': round(us_price / vcpu, 2),
            'price_per_gb_ram': round(us_price / ram_gb, 2),
            'price_per_gb_storage': round(us_price / storage_gb, 4)
        }
    
    if global_price_usd and global_price_usd > 0:
        result['global'] = {
            'price_per_vcpu': round(global_price_usd / vcpu, 2),
            'price_per_gb_ram': round(global_price_usd / ram_gb, 2),
            'price_per_gb_storage': round(global_price_usd / storage_gb, 4)
        }
    
    # Determine best region for each resource type
    if result['us'] and result['global']:
        result['best_for_cpu'] = 'US' if result['us']['price_per_vcpu'] <= result['global']['price_per_vcpu'] else 'Global'
        result['best_for_ram'] = 'US' if result['us']['price_per_gb_ram'] <= result['global']['price_per_gb_ram'] else 'Global'
        result['best_for_storage'] = 'US' if result['us']['price_per_gb_storage'] <= result['global']['price_per_gb_storage'] else 'Global'
    elif result['us']:
        result['best_for_cpu'] = 'US'
        result['best_for_ram'] = 'US'
        result['best_for_storage'] = 'US'
    elif result['global']:
        result['best_for_cpu'] = 'Global'
        result['best_for_ram'] = 'Global'
        result['best_for_storage'] = 'Global'
    
    return result


def calculate_best_value_recommendations(comparisons: List[Dict]) -> Dict:
    """
    Find the best value plans for different use cases.
    
    Returns recommendations for:
    - Best $/vCPU (CPU-intensive workloads)
    - Best $/GB RAM (memory-intensive workloads)
    - Best $/GB storage (storage-intensive workloads)
    - Best overall value (balanced score) - US pricing only to avoid duplicates
    """
    cpu_values = []
    ram_values = []
    storage_values = []
    overall_values = []
    
    for plan in comparisons:
        eff = plan.get('cost_efficiency')
        if not eff:
            continue
        
        # Only consider plans that are orderable and available
        is_orderable = plan.get('is_orderable', True)
        us_available = plan.get('us', {}).get('available_count', 0) > 0 if plan.get('us') else False
        global_available = plan.get('global', {}).get('available_count', 0) > 0 if plan.get('global') else False
        
        if not is_orderable:
            continue
        
        vcpu = eff.get('vcpu', 0)
        ram_gb = eff.get('ram_gb', 0)
        storage_gb = eff.get('storage_gb', 0)
            
        if eff.get('us') and us_available:
            price = plan['us'].get('price_usd')
            plan_entry = {
                'plan': plan['base_plan'],
                'display_name': plan.get('display_name'),
                'region': 'US',
                'specs': f"{vcpu} vCPU, {ram_gb}GB RAM, {storage_gb}GB",
                'price': price,
                'vcpu': vcpu,
                'ram_gb': ram_gb,
                'storage_gb': storage_gb
            }
            cpu_values.append({**plan_entry, 'value': eff['us']['price_per_vcpu']})
            ram_values.append({**plan_entry, 'value': eff['us']['price_per_gb_ram']})
            storage_values.append({**plan_entry, 'value': eff['us']['price_per_gb_storage']})
            
            # Calculate overall value score (weighted average of normalized metrics)
            # Lower is better for each, so we calculate a combined score
            # Only use US pricing for overall recommendations to avoid duplicate plans
            if price and price > 0:
                # Score = price / (vcpu + ram_gb/4 + storage_gb/50) - balanced weighting
                resource_score = vcpu + (ram_gb / 4) + (storage_gb / 50)
                overall_score = price / resource_score if resource_score > 0 else float('inf')
                overall_values.append({
                    **plan_entry,
                    'value': round(overall_score, 2),
                    'value_label': f"${overall_score:.2f}/unit"
                })
            
        if eff.get('global') and global_available:
            price = plan['global'].get('price_usd')
            plan_entry = {
                'plan': plan['base_plan'],
                'display_name': plan.get('display_name'),
                'region': 'Global',
                'specs': f"{vcpu} vCPU, {ram_gb}GB RAM, {storage_gb}GB",
                'price': price,
                'vcpu': vcpu,
                'ram_gb': ram_gb,
                'storage_gb': storage_gb
            }
            cpu_values.append({**plan_entry, 'value': eff['global']['price_per_vcpu']})
            ram_values.append({**plan_entry, 'value': eff['global']['price_per_gb_ram']})
            storage_values.append({**plan_entry, 'value': eff['global']['price_per_gb_storage']})
            # Note: Global plans are NOT added to overall_values to avoid duplicates
            # Overall recommendations use US pricing only
    
    # Sort by value (lower is better)
    cpu_values.sort(key=lambda x: x['value'])
    ram_values.sort(key=lambda x: x['value'])
    storage_values.sort(key=lambda x: x['value'])
    overall_values.sort(key=lambda x: x['value'])
    
    return {
        'best_overall': overall_values[:5] if overall_values else [],
        'best_for_cpu': cpu_values[:5] if cpu_values else [],
        'best_for_ram': ram_values[:5] if ram_values else [],
        'best_for_storage': storage_values[:5] if storage_values else [],
        'metrics': {
            'overall_label': 'Value Score',
            'cpu_label': '$/vCPU',
            'ram_label': '$/GB RAM', 
            'storage_label': '$/GB Storage'
        }
    }


def get_base_plan(plan_code: str) -> str:
    """Extract base plan name for matching across regions."""
    base = plan_code
    # Remove LZ suffixes first
    if '.LZ-eu' in base:
        base = base.replace('.LZ-eu', '')
    elif '.LZ-ca' in base:
        base = base.replace('.LZ-ca', '')
    elif '.LZ' in base:
        base = base.replace('.LZ', '')
    # Remove region suffixes
    if base.endswith('-eu'):
        base = base[:-3]
    elif base.endswith('-ca'):
        base = base[:-3]
    return base


@router.get("/api/compare")
async def compare_subsidiaries():
    """
    Compare prices and availability between US and Global (FR) subsidiaries.
    
    Returns plans with data from both regions for side-by-side comparison,
    with prices converted to a common currency (USD) for accurate comparison.
    """
    # Get status for both US and FR (Global)
    us_status = await db.get_current_status('US')
    fr_status = await db.get_current_status('FR')
    
    # Get current EUR to USD rate
    eur_usd_rate = await converter.get_eur_to_usd_rate()
    
    # Build lookup dictionaries by plan_code
    us_by_plan = {}
    for item in us_status:
        plan = item['plan_code']
        if plan not in us_by_plan:
            us_by_plan[plan] = {
                'plan_code': plan,
                'display_name': item.get('display_name'),
                'specs': item.get('specs'),
                'vcpu': item.get('vcpu'),
                'ram_gb': item.get('ram_gb'),
                'storage_gb': item.get('storage_gb'),
                'storage_type': item.get('storage_type'),
                'bandwidth_mbps': item.get('bandwidth_mbps'),
                'is_orderable': item.get('is_orderable'),
                'product_line': item.get('product_line'),
                'price': item.get('price'),
                'price_microcents': item.get('price_microcents'),
                'currency': item.get('currency', 'USD'),
                'purchase_url': item.get('purchase_url'),
                'datacenters': [],
                'available_count': 0,
                'total_count': 0
            }
        us_by_plan[plan]['datacenters'].append({
            'datacenter': item['datacenter'],
            'datacenter_code': item.get('datacenter_code'),
            'is_available': item['is_available'],
            'location_display_name': item.get('location_display_name'),
            'location_country': item.get('location_country'),
            'location_flag': item.get('location_flag')
        })
        us_by_plan[plan]['total_count'] += 1
        if item['is_available']:
            us_by_plan[plan]['available_count'] += 1
    
    fr_by_plan = {}
    for item in fr_status:
        plan = item['plan_code']
        if plan not in fr_by_plan:
            fr_by_plan[plan] = {
                'plan_code': plan,
                'display_name': item.get('display_name'),
                'specs': item.get('specs'),
                'vcpu': item.get('vcpu'),
                'ram_gb': item.get('ram_gb'),
                'storage_gb': item.get('storage_gb'),
                'storage_type': item.get('storage_type'),
                'bandwidth_mbps': item.get('bandwidth_mbps'),
                'is_orderable': item.get('is_orderable'),
                'product_line': item.get('product_line'),
                'price': item.get('price'),
                'price_microcents': item.get('price_microcents'),
                'currency': item.get('currency', 'EUR'),
                'purchase_url': item.get('purchase_url'),
                'datacenters': [],
                'available_count': 0,
                'total_count': 0
            }
        fr_by_plan[plan]['datacenters'].append({
            'datacenter': item['datacenter'],
            'datacenter_code': item.get('datacenter_code'),
            'is_available': item['is_available'],
            'location_display_name': item.get('location_display_name'),
            'location_country': item.get('location_country'),
            'location_flag': item.get('location_flag')
        })
        fr_by_plan[plan]['total_count'] += 1
        if item['is_available']:
            fr_by_plan[plan]['available_count'] += 1
    
    # Group by base plan name
    comparison = {}
    
    for plan_code, data in us_by_plan.items():
        base = get_base_plan(plan_code)
        if base not in comparison:
            comparison[base] = {
                'base_plan': base,
                'display_name': data.get('display_name', '').replace(' (Local Zone)', '').replace(' (EU)', '').replace(' (Canada)', '').strip(),
                'specs': data.get('specs'),
                'vcpu': data.get('vcpu'),
                'ram_gb': data.get('ram_gb'),
                'storage_gb': data.get('storage_gb'),
                'storage_type': data.get('storage_type'),
                'bandwidth_mbps': data.get('bandwidth_mbps'),
                'is_orderable': data.get('is_orderable'),
                'product_line': data.get('product_line'),
                'us': None,
                'global': None,
                'price_comparison': None
            }
        comparison[base]['us'] = {
            'plan_code': plan_code,
            'price': data.get('price'),  # Formatted string like "$5.99/mo"
            'price_microcents': data.get('price_microcents'),
            'currency': data.get('currency', 'USD'),
            'price_usd': data.get('price_microcents') / 100_000_000 if data.get('price_microcents') else None,  # Numeric USD
            'purchase_url': data.get('purchase_url'),
            'available_count': data['available_count'],
            'total_count': data['total_count'],
            'datacenters': data['datacenters']
        }
    
    for plan_code, data in fr_by_plan.items():
        base = get_base_plan(plan_code)
        if base not in comparison:
            comparison[base] = {
                'base_plan': base,
                'display_name': data.get('display_name', '').replace(' (EU Local Zone)', '').replace(' (EU)', '').replace(' (Canada)', '').strip(),
                'specs': data.get('specs'),
                'vcpu': data.get('vcpu'),
                'ram_gb': data.get('ram_gb'),
                'storage_gb': data.get('storage_gb'),
                'storage_type': data.get('storage_type'),
                'bandwidth_mbps': data.get('bandwidth_mbps'),
                'is_orderable': data.get('is_orderable'),
                'product_line': data.get('product_line'),
                'us': None,
                'global': None,
                'price_comparison': None
            }
        
        # Convert EUR price to USD using price_microcents for accurate numeric calculation
        eur_price_microcents = data.get('price_microcents')
        eur_price_numeric = eur_price_microcents / 100_000_000 if eur_price_microcents else None
        usd_price = eur_price_numeric * eur_usd_rate if eur_price_numeric else None
        
        comparison[base]['global'] = {
            'plan_code': plan_code,
            'price': data.get('price'),  # Formatted string like "€5.99/mo"
            'price_microcents': eur_price_microcents,
            'currency': data.get('currency', 'EUR'),
            'price_usd': round(usd_price, 2) if usd_price else None,  # Converted to USD
            'purchase_url': data.get('purchase_url'),
            'available_count': data['available_count'],
            'total_count': data['total_count'],
            'datacenters': data['datacenters']
        }
    
    # Calculate price comparisons and cost efficiency metrics
    for base, data in comparison.items():
        us_data = data.get('us')
        global_data = data.get('global')
        
        us_price = us_data.get('price_usd') if us_data else None
        # Get numeric EUR price from microcents
        global_price_microcents = global_data.get('price_microcents') if global_data else None
        global_price_eur = global_price_microcents / 100_000_000 if global_price_microcents else None
        global_price_usd = global_data.get('price_usd') if global_data else None
        
        data['price_comparison'] = calculate_price_difference(
            us_price,
            global_price_eur,
            global_price_usd
        )
        
        # Calculate cost efficiency metrics ($/unit)
        data['cost_efficiency'] = calculate_cost_efficiency(data, us_price, global_price_usd)
    
    # Convert to list and sort by product line, then plan name
    result = list(comparison.values())
    result.sort(key=lambda x: (
        0 if x.get('product_line') == '2025' else 1,
        0 if x.get('is_orderable') else 1,
        x['base_plan']
    ))
    
    # Calculate best value recommendations
    recommendations = calculate_best_value_recommendations(result)
    
    return {
        'comparisons': result,
        'exchange_rate': {
            'eur_usd': round(eur_usd_rate, 4),
            **converter.get_rate_info()
        },
        'recommendations': recommendations,
        'summary': {
            'us_plans': len(us_by_plan),
            'global_plans': len(fr_by_plan),
            'comparable_plans': len([c for c in result if c['us'] and c['global']]),
            'us_cheaper': len([c for c in result if c.get('price_comparison', {}).get('cheaper_region') == 'US']),
            'global_cheaper': len([c for c in result if c.get('price_comparison', {}).get('cheaper_region') == 'Global']),
            'same_price': len([c for c in result if c.get('price_comparison', {}).get('cheaper_region') is None and c.get('price_comparison') is not None])
        }
    }


@router.get("/api/exchange-rate")
async def get_exchange_rate():
    """Get current exchange rate information."""
    eur_usd = await converter.get_eur_to_usd_rate()
    return {
        'eur_usd': round(eur_usd, 4),
        'usd_eur': round(1 / eur_usd, 4),
        **converter.get_rate_info()
    }
