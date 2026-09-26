# /card_generator/validator.py

from typing import Dict, Any, List

class Validator:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_and_report(self, card_data: Dict[str, Any], balance_info: Dict[str, Any], balancer_config: Dict[str, Any]):
        self.errors = []
        self.warnings = []
        self._validate(card_data, balance_info['total_pp'], balancer_config)
        
        print("--- CARD VALIDATION REPORT ---")
        print(f"Generated Card Name: '{card_data['name']}'")
        print(f"Type: {card_data['type']} | Rarity: {card_data['rarity']} | Cost: {card_data['cost']}")
        print("-" * 30)
        print("EFFECTS:")
        for effect in card_data['effects']:
            print(f"- {self._format_effect(effect)}")
        print("-" * 30)
        
        print("BALANCE CALCULATION:")
        for item in balance_info['pp_breakdown']:
            if isinstance(item.get('effect'), str):
                print(f"- {item['reason']:<35} | PP: {item['pp']:>5.1f}")
            elif item.get('effect'):
                effect_str = self._format_effect(item['effect'].__dict__)
                print(f"- {effect_str:<35} | PP: {item['pp']:>5.1f} | ({item['reason']})")
            else:
                 print(f"- {item['reason']:<35} | PP: {item['pp']:>5.1f}")

        
        print("-" * 30)
        print(f"Total Power Points (PP): {balance_info['total_pp']:.2f}")
        print(f"Final Energy Cost: {card_data['cost']}")
        print("-" * 30)
        
        if self.errors or self.warnings:
            print("VALIDATION STATUS: ISSUES FOUND")
            for error in self.errors:
                print(f"- ERROR: {error}")
            for warning in self.warnings:
                print(f"- WARNING: {warning}")
        else:
            print("VALIDATION STATUS: PASSED")
        print("=" * 32)
        print("\n")

    def _format_effect(self, effect: Dict[str, Any]) -> str:
        action = effect.get('action', 'N/A').capitalize()
        value = effect.get('value', '')
        target = effect.get('target', 'N/A')
        
        if action == "Applystatus":
            return f"ApplyStatus ({effect.get('status')}) | Value: {value}, Target: {target}"
        if action == "Addcardtopile":
            return f"AddCard ({effect.get('card_to_add')}) | Value: {value}, Pile: {effect.get('target_pile')}"
        if action == "Targetedexhaust":
            return f"Exhaust | Value: {value}, From: {effect.get('target_pile')}"
        
        return f"{action} | Value: {value}, Target: {target}"


    def _validate(self, card_data: Dict[str, Any], total_pp: float, config: Dict[str, Any]):
        card_type = card_data['type']
        rarity = card_data['rarity']
        cost = card_data['cost']
        effects = card_data['effects']
        
        if cost < -1:
            self.errors.append("Card cost cannot be less than -1.")
        
        if not effects:
            self.errors.append("Card must have at least one effect.")
            
        if card_type == "Attack":
            has_damage = any(e['action'].upper() == 'DEALATTACKDAMAGE' for e in effects)
            if not has_damage:
                self.errors.append("Attack card must have a 'DEALATTACKDAMAGE' effect.")

        if card_type == "Power":
            has_invalid_action = any(e['action'].upper() in ['DEALATTACKDAMAGE', 'GAINBLOCK'] for e in effects)
            if has_invalid_action:
                self.errors.append("Power card cannot have 'DEALATTACKDAMAGE' or 'GAINBLOCK' effects.")
        for effect in effects:
            action = effect['action'].upper()
            if action == "APPLYSTATUS" and not effect.get('status'):
                self.errors.append("An 'ApplyStatus' effect is missing its 'status' field.")
            if action == "ADDCARDTOPILE" and not effect.get('card_to_add'):
                self.errors.append("An 'AddCardToPile' effect is missing 'card_to_add'.")
            if action == "ADDCARDTOPILE" and not effect.get('target_pile'):
                self.errors.append("An 'AddCardToPile' effect is missing 'target_pile'.")
            if action == "TARGETEDEXHAUST" and not effect.get('target_pile'):
                self.errors.append("A 'TargetedExhaust' effect is missing 'target_pile'.")

        if cost != -1:
            thresholds = config['rarity_thresholds']
            if rarity == "Common" and total_pp > thresholds['Common']:
                self.warnings.append(f"Heuristic Mismatch: Card is 'Common' but PP ({total_pp:.1f}) exceeds Common threshold ({thresholds['Common']}).")
            
            if rarity == "Uncommon" and (total_pp <= thresholds['Common'] or total_pp > thresholds['Uncommon']):
                self.warnings.append(f"Heuristic Mismatch: Card is 'Uncommon' but PP ({total_pp:.1f}) is outside Uncommon bracket ({thresholds['Common']}-{thresholds['Uncommon']}).")

            if rarity == "Rare" and total_pp <= thresholds['Uncommon']:
                self.warnings.append(f"Heuristic Mismatch: Card is 'Rare' but PP ({total_pp:.1f}) is below Rare threshold ({thresholds['Uncommon']}).")

