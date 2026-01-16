from decimal import Decimal, ROUND_HALF_UP
from cases.models import Heir
from collections import defaultdict

class InheritanceEngine:
    def __init__(self, net_estate, heirs_data):
        self.net_estate = Decimal(net_estate)
        self.heirs = heirs_data
        self.shares = {} 
        self.total_shares_fraction = Decimal(0)
        self.blocked_heirs = []
        self.active_heirs = []

    def calculate(self):
        # Reset
        self.shares = {}
        self.total_shares_fraction = Decimal(0)
        self.blocked_heirs = []
        self.active_heirs = []

        # 0. Basic Pre-processing
        # Filter explicitly blocked heirs (e.g. difference of religion, homicide - if flagged is_blocked=True in DB)
        self.active_heirs = [h for h in self.heirs if not h.is_blocked]

        # 1. Apply Blocking Rules (Hajb)
        self.apply_blocking_rules()

        # 2. Assign Faraid (Fixed Shares)
        remaining_after_faraid = self.assign_fixed_shares()

        # 3. Assign Asabah (Residuary)
        self.assign_residuary_shares(remaining_after_faraid)

        # 4. Handle Awal (Increase) and Radd (Return)
        self.handle_awal_and_radd()

        # 5. Calculate Final Values
        self.finalize_values()

        return self.shares

    def apply_blocking_rules(self):
        """
        Determines who is blocked (محجوب) by whom.
        Updates self.active_heirs and self.blocked_heirs.
        """
        # Definitions of presence
        sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON]
        sons_of_sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_SON]
        father = [h for h in self.active_heirs if h.relationship == Heir.Relationship.FATHER]
        grandfather = [h for h in self.active_heirs if h.relationship == Heir.Relationship.GRANDFATHER_FATHER]
        
        # Male Descendants block many
        has_son = len(sons) > 0
        has_son_of_son = len(sons_of_sons) > 0
        has_male_descendant = has_son or has_son_of_son
        
        # Father blocks many
        has_father = len(father) > 0
        
        to_block = []

        for heir in self.active_heirs:
            blocked = False
            blocking_reason = ""
            r = heir.relationship
            
            # --- Blocking Logic ---
            
            # Grandchildren (Son/Daughter of Son) are blocked by Son
            if r in [Heir.Relationship.SON_OF_SON, Heir.Relationship.DAUGHTER_OF_SON]:
                if has_son:
                    blocked = True
                    blocker_name = sons[0].name
                    blocking_reason = f"تم الحجب بواسطة الابن ({blocker_name})"
            
            # Lower Son of Son blocked by Higher Son of Son (Simplified for now)

            # Grandfather/Grandmother
            if r == Heir.Relationship.GRANDFATHER_FATHER: # Paternal Grandfather
                if has_father:
                    blocked = True
                    blocker_name = father[0].name
                    blocking_reason = f"تم الحجب بواسطة الأب ({blocker_name})"
            
            if r in [Heir.Relationship.GRANDMOTHER_FATHER, Heir.Relationship.GRANDMOTHER_MOTHER]:
                # Mother blocks all Grandmothers
                mothers = [h for h in self.active_heirs if h.relationship == Heir.Relationship.MOTHER]
                if mothers:
                    blocked = True
                    blocker_name = mothers[0].name
                    blocking_reason = f"تم الحجب بواسطة الأم ({blocker_name})"
                # Father blocks Paternal Grandmother only
                elif r == Heir.Relationship.GRANDMOTHER_FATHER and has_father:
                    blocked = True
                    blocker_name = father[0].name
                    blocking_reason = f"تم الحجب بواسطة الأب ({blocker_name})"
            
            # Siblings (All types) are blocked by Son, Son of Son, and Father
            is_sibling = r in [
                Heir.Relationship.BROTHER, Heir.Relationship.SISTER,
                Heir.Relationship.BROTHER_FATHER, Heir.Relationship.SISTER_FATHER,
                Heir.Relationship.BROTHER_MOTHER, Heir.Relationship.SISTER_MOTHER
            ]
            if is_sibling:
                if has_son:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة الابن ({sons[0].name})"
                elif has_son_of_son:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة ابن الابن ({sons_of_sons[0].name})"
                elif has_father:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة الأب ({father[0].name})"
            
            # Specific Sibling Blocking
            if not blocked and is_sibling:
                # Paternal Siblings blocked by Full Brother
                if r in [Heir.Relationship.BROTHER_FATHER, Heir.Relationship.SISTER_FATHER]:
                    full_brothers = [h for h in self.active_heirs if h.relationship == Heir.Relationship.BROTHER]
                    if full_brothers:
                        blocked = True
                        blocking_reason = f"تم الحجب بواسطة الأخ الشقيق ({full_brothers[0].name})"

            # Maternal Siblings (Akh li Om)
            if not blocked and r in [Heir.Relationship.BROTHER_MOTHER, Heir.Relationship.SISTER_MOTHER]:
                # Blocked by any Branch or Male Root
                # Checked above generally, but specifically:
                daughters = [h for h in self.active_heirs if h.relationship == Heir.Relationship.DAUGHTER]
                gd_daughters = [h for h in self.active_heirs if h.relationship == Heir.Relationship.DAUGHTER_OF_SON]
                grandfathers = [h for h in self.active_heirs if h.relationship == Heir.Relationship.GRANDFATHER_FATHER]
                
                if daughters:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة البنت ({daughters[0].name})"
                elif gd_daughters:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة بنت الابن ({gd_daughters[0].name})"
                elif grandfathers:
                    blocked = True
                    blocking_reason = f"تم الحجب بواسطة الجد ({grandfathers[0].name})"

            # Uncles and Cousins
            is_uncle_or_cousin = r in [
                Heir.Relationship.UNCLE, Heir.Relationship.UNCLE_FATHER,
                Heir.Relationship.SON_OF_UNCLE, Heir.Relationship.SON_OF_UNCLE_FATHER,
                Heir.Relationship.SON_OF_BROTHER, Heir.Relationship.SON_OF_BROTHER_FATHER
            ]
            
            if not blocked and is_uncle_or_cousin:
                # Blocked by Son, Grandson, Father, Grandfather
                if has_male_descendant:
                     blocked = True
                     reason_src = sons[0] if sons else sons_of_sons[0]
                     blocking_reason = f"تم الحجب بواسطة الفرع الوارث الذكر ({reason_src.name})"
                elif has_father:
                     blocked = True
                     blocking_reason = f"تم الحجب بواسطة الأب ({father[0].name})"
                elif grandfather: # has_grandfather logic
                     gf = [h for h in self.active_heirs if h.relationship == Heir.Relationship.GRANDFATHER_FATHER]
                     if gf: 
                         blocked = True
                         blocking_reason = f"تم الحجب بواسطة الجد ({gf[0].name})"
                
                # Blocked by Brothers (Full or Paternal)
                if not blocked:
                     bros = [h for h in self.active_heirs if h.relationship in [Heir.Relationship.BROTHER, Heir.Relationship.BROTHER_FATHER]]
                     if bros:
                         blocked = True
                         blocking_reason = f"تم الحجب بواسطة الأخ ({bros[0].name})"
                
                # Detailed prioritization (simplified)
                # Full Uncle blocks Paternal Uncle
                if not blocked and r == Heir.Relationship.UNCLE_FATHER:
                    uncles = [h for h in self.active_heirs if h.relationship == Heir.Relationship.UNCLE]
                    if uncles:
                        blocked = True
                        blocking_reason = f"تم الحجب بواسطة العم الشقيق ({uncles[0].name})"
            
            if blocked:
                to_block.append((heir, blocking_reason))

        for h, reason in to_block:
            if h in self.active_heirs:
                self.active_heirs.remove(h)
                self.blocked_heirs.append(h)
                self.shares[h.id] = {
                    'fraction': 'محجوب',
                    'blocking_reason': reason,
                    'percentage': Decimal(0),
                    'value': Decimal(0),
                    'raw_share': Decimal(0),
                    'is_blocked': True
                }

    def assign_fixed_shares(self):
        """
        Assigns standard Faraid portions (1/2, 1/4, 1/8, 2/3, 1/3, 1/6).
        Returns the remaining share fraction (1 - total_assigned).
        """
        # Helpers
        def get_count(rels):
            return len([h for h in self.active_heirs if h.relationship in rels])
        
        has_son = get_count([Heir.Relationship.SON]) > 0
        has_son_of_son = get_count([Heir.Relationship.SON_OF_SON]) > 0
        has_daughter = get_count([Heir.Relationship.DAUGHTER]) > 0
        has_daughter_of_son = get_count([Heir.Relationship.DAUGHTER_OF_SON]) > 0
        
        has_descendant = has_son or has_son_of_son or has_daughter or has_daughter_of_son
        has_male_descendant = has_son or has_son_of_son
        
        has_siblings_multiple_or_mix = len([h for h in self.active_heirs if 'BROTHER' in h.relationship or 'SISTER' in h.relationship]) > 1

        total_faraid_share = Decimal(0)

        for heir in self.active_heirs:
            share = Decimal(0)
            fraction_str = ""
            r = heir.relationship

            # --- Husband ---
            if r == Heir.Relationship.HUSBAND:
                if has_descendant:
                    share = Decimal(1)/Decimal(4)
                    fraction_str = "1/4"
                else:
                    share = Decimal(1)/Decimal(2)
                    fraction_str = "1/2"

            # --- Wife ---
            elif r == Heir.Relationship.WIFE:
                wives_count = get_count([Heir.Relationship.WIFE])
                if has_descendant:
                    base = Decimal(1)/Decimal(8)
                    share = base / Decimal(wives_count)
                    fraction_str = "1/8" if wives_count == 1 else f"1/8 divided by {wives_count}"
                else:
                    base = Decimal(1)/Decimal(4)
                    share = base / Decimal(wives_count)
                    fraction_str = "1/4" if wives_count == 1 else f"1/4 divided by {wives_count}"

            # --- Father ---
            elif r == Heir.Relationship.FATHER:
                if has_male_descendant:
                    share = Decimal(1)/Decimal(6)
                    fraction_str = "1/6"
                elif has_descendant: # Only Female descendants
                    share = Decimal(1)/Decimal(6) # 1/6 + Asabah (handled later)
                    fraction_str = "1/6 + عصبة"
                # If no descendants, Father is purely Asabah (No Fixed Share initially)

            # --- Mother ---
            elif r == Heir.Relationship.MOTHER:
                if has_descendant or has_siblings_multiple_or_mix:
                    share = Decimal(1)/Decimal(6)
                    fraction_str = "1/6"
                else:
                    # Umariyatan case check (Spouse + Mother + Father) - Mother gets 1/3 of remainder?
                    # Simplified for now: Standard 1/3
                    # TODO: Implement Umariyatan
                    share = Decimal(1)/Decimal(3)
                    fraction_str = "1/3"

            # --- Grandfather ---
            elif r == Heir.Relationship.GRANDFATHER_FATHER:
                # Same as Father if Father is missing
                if has_male_descendant:
                    share = Decimal(1)/Decimal(6)
                    fraction_str = "1/6"
                elif has_descendant:
                    share = Decimal(1)/Decimal(6)
                    fraction_str = "1/6 + عصبة"
            
            # --- Grandmother ---
            elif r in [Heir.Relationship.GRANDMOTHER_FATHER, Heir.Relationship.GRANDMOTHER_MOTHER]:
                # 1/6 shared
                gm_count = get_count([Heir.Relationship.GRANDMOTHER_FATHER, Heir.Relationship.GRANDMOTHER_MOTHER])
                share = (Decimal(1)/Decimal(6)) / Decimal(gm_count)
                fraction_str = "1/6"
            
            # --- Daughters ---
            elif r == Heir.Relationship.DAUGHTER:
                if not has_son: # If Son exists, she is Asabah (handled later)
                    d_count = get_count([Heir.Relationship.DAUGHTER])
                    if d_count == 1:
                        share = Decimal(1)/Decimal(2)
                        fraction_str = "1/2"
                    else:
                        share = (Decimal(2)/Decimal(3)) / Decimal(d_count)
                        fraction_str = "2/3"
            
            # --- Daughter of Son ---
            elif r == Heir.Relationship.DAUGHTER_OF_SON:
                if not has_son and not has_son_of_son: # If Male counterpart exists, Asabah
                    # Check Daughters
                    d_count = get_count([Heir.Relationship.DAUGHTER])
                    ds_count = get_count([Heir.Relationship.DAUGHTER_OF_SON])
                    
                    if d_count == 0:
                        if ds_count == 1:
                            share = Decimal(1)/Decimal(2)
                            fraction_str = "1/2"
                        else:
                            share = (Decimal(2)/Decimal(3)) / Decimal(ds_count)
                            fraction_str = "2/3"
                    elif d_count == 1:
                        # Takmilat al-Thuluthayn (Complement to 2/3)
                        share = (Decimal(1)/Decimal(6)) / Decimal(ds_count)
                        fraction_str = "1/6 (Takmila)"
                    # If d_count >= 2, no share unless "Blessed Brother" (not implemented yet)
            
            # --- Sisters (Full) ---
            elif r == Heir.Relationship.SISTER:
                # Conditions: No Descendants, No Father/GF
                # Also check: No Brother (Asabah)
                has_brother = get_count([Heir.Relationship.BROTHER]) > 0
                has_female_descendant = has_daughter or has_daughter_of_son
                
                if not has_brother and not has_male_descendant and not has_father and not has_female_descendant:
                    s_count = get_count([Heir.Relationship.SISTER])
                    if s_count == 1:
                        share = Decimal(1)/Decimal(2)
                        fraction_str = "1/2"
                    else:
                        share = (Decimal(2)/Decimal(3)) / Decimal(s_count)
                        fraction_str = "2/3"
                # Note: If Female Descendant exists, Sister becomes Asabah ma'a al-Ghayr (handled later)

            # --- Maternal Siblings (Akh/Okht li Om) ---
            elif r in [Heir.Relationship.BROTHER_MOTHER, Heir.Relationship.SISTER_MOTHER]:
                # Already checked blocking
                m_sibs_count = get_count([Heir.Relationship.BROTHER_MOTHER, Heir.Relationship.SISTER_MOTHER])
                if m_sibs_count == 1:
                    share = Decimal(1)/Decimal(6)
                    fraction_str = "1/6"
                else:
                    share = (Decimal(1)/Decimal(3)) / Decimal(m_sibs_count)
                    fraction_str = "1/3"

            if share > 0:
                self.shares[heir.id] = {
                    'fraction': fraction_str,
                    'raw_share': share,
                    'is_fixed': True
                }
                total_faraid_share += share

        self.total_shares_fraction = total_faraid_share
        return Decimal(1) - total_faraid_share

    def assign_residuary_shares(self, remaining_share):
        """
        Assigns shares to Asabah (Residuary) according to priority and Ta'sib rules.
        """
        if remaining_share <= 0:
            return

        asabah_group = []
        
        # Priority 1: Son & Daughter (Ta'sib bil-Ghayr)
        sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON]
        daughters = [h for h in self.active_heirs if h.relationship == Heir.Relationship.DAUGHTER]
        
        if sons:
            asabah_group = sons + daughters
        else:
            # Priority 2: Son of Son & Daughter of Son
            sons_of_sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_SON]
            daughters_of_sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.DAUGHTER_OF_SON] # Only if not already took Faraid? 
            # Actually, if Son of Son exists, Daughter of Son loses Faraid and becomes Asabah
            if sons_of_sons:
                # Should remove D_O_S fixed share if any and add to group?
                # For simplicity assuming calculate() removed fixed share if male counterpart exists properly in Step 2 logic (added checks there)
                asabah_group = sons_of_sons + daughters_of_sons
        
        active_asabah_group = []
        
        # Filter Logic: The loop below finds the FIRST valid Asabah group and assigns remainder
        
        # 1. Sons/Daughters
        if sons:
             self._distribute_asabah(remaining_share, sons, daughters)
             return
             
        # 2. Sons of Sons
        sons_of_sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_SON]
        daughters_of_sons = [h for h in self.active_heirs if h.relationship == Heir.Relationship.DAUGHTER_OF_SON]
        if sons_of_sons:
             # If they had fixed shares, they shouldn't have been assigned in step 2 if SoS exists. 
             self._distribute_asabah(remaining_share, sons_of_sons, daughters_of_sons)
             return

        # 3. Father
        father = [h for h in self.active_heirs if h.relationship == Heir.Relationship.FATHER]
        if father:
            # Father takes all remainder (plus his 1/6 if he had it?)
            # If he had 1/6, he keeps it and adds remainder.
            # My structure adds to existing share if present.
            self._distribute_add_to_existing(remaining_share, father[0], " + عصبة")
            return
            
        # 4. Grandfather (if no Father)
        grandfather = [h for h in self.active_heirs if h.relationship == Heir.Relationship.GRANDFATHER_FATHER]
        if grandfather:
            self._distribute_add_to_existing(remaining_share, grandfather[0], " + عصبة")
            return
            
        # 5. Brothers/Sisters (Siblings)
        # Check Asabah Ma'a al-Ghayr (Sisters with Daughters)
        daughters_any = [h for h in self.active_heirs if h.relationship in [Heir.Relationship.DAUGHTER, Heir.Relationship.DAUGHTER_OF_SON]]
        sisters_full = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SISTER]
        sisters_paternal = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SISTER_FATHER]
        
        if daughters_any and (sisters_full or sisters_paternal):
            # Sisters become Asabah. Full Sister takes priority over Paternal.
            if sisters_full:
                self._distribute_asabah(remaining_share, [], sisters_full) # Treated as Asabah (usually treated as strong as Brother here)
                return
            elif sisters_paternal:
                self._distribute_asabah(remaining_share, [], sisters_paternal)
                return
        
        # Standard Ta'sib bil-Ghayr (Brother + Sister) or bin-Nafs (Brother only)
        brothers = [h for h in self.active_heirs if h.relationship == Heir.Relationship.BROTHER]
        if brothers:
            self._distribute_asabah(remaining_share, brothers, sisters_full)
            return
            
        brothers_paternal = [h for h in self.active_heirs if h.relationship == Heir.Relationship.BROTHER_FATHER]
        if brothers_paternal:
            self._distribute_asabah(remaining_share, brothers_paternal, sisters_paternal)
            return

        # 6. Nephews (Sons of Brother) - Full then Paternal
        son_bro = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_BROTHER]
        if son_bro:
            self._distribute_asabah(remaining_share, son_bro, [])
            return
            
        son_bro_f = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_BROTHER_FATHER]
        if son_bro_f:
            self._distribute_asabah(remaining_share, son_bro_f, [])
            return

        # 7. Uncles - Full then Paternal
        uncle = [h for h in self.active_heirs if h.relationship == Heir.Relationship.UNCLE]
        if uncle:
            self._distribute_asabah(remaining_share, uncle, [])
            return

        uncle_f = [h for h in self.active_heirs if h.relationship == Heir.Relationship.UNCLE_FATHER]
        if uncle_f:
            self._distribute_asabah(remaining_share, uncle_f, [])
            return
            
        # 8. Cousins
        son_uncle = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_UNCLE]
        if son_uncle:
            self._distribute_asabah(remaining_share, son_uncle, [])
            return
            
        son_uncle_f = [h for h in self.active_heirs if h.relationship == Heir.Relationship.SON_OF_UNCLE_FATHER]
        if son_uncle_f:
            self._distribute_asabah(remaining_share, son_uncle_f, [])
            return

    def _distribute_asabah(self, total_share, males, females):
        if not males and not females:
            return
            
        unit_weight = len(males) * 2 + len(females)
        if unit_weight == 0: return # Avoid div/0
        
        unit_share = total_share / Decimal(unit_weight)
        
        for m in males:
            self._set_share(m, unit_share * 2, "عصبة")
            
        for f in females:
            self._set_share(f, unit_share, "عصبة")

    def _distribute_add_to_existing(self, share_amount, heir, extra_label):
        if heir.id in self.shares:
            curr = self.shares[heir.id]
            curr['raw_share'] += share_amount
            curr['fraction'] += extra_label
        else:
            self.shares[heir.id] = {
                'fraction': 'عصبة',
                'raw_share': share_amount,
                'is_fixed': False
            }

    def _set_share(self, heir, share, label):
        self.shares[heir.id] = {
            'fraction': label,
            'raw_share': share,
            'is_fixed': False
        }

    def handle_awal_and_radd(self):
        total_share = sum(s['raw_share'] for s in self.shares.values())
        
        if total_share == 0: return

        # Awal: Total shares > 1
        if total_share > Decimal(1) + Decimal('0.0001'): # Epsilon for float issues
            # Reduce all shares proportionally
            for hid in self.shares:
                self.shares[hid]['raw_share'] /= total_share
                self.shares[hid]['fraction'] += " (Awal)"
        
        # Radd: Total shares < 1
        elif total_share < Decimal(1) - Decimal('0.0001'):
            # Return remainder to Faraid heirs (except spouses)
            # Find eligible for Radd
            eligible_ids = []
            eligible_total = Decimal(0)
            
            for hid, data in self.shares.items():
                # Get Heir object
                heir = next(h for h in self.heirs if h.id == hid)
                if heir.relationship not in [Heir.Relationship.HUSBAND, Heir.Relationship.WIFE]:
                    eligible_ids.append(hid)
                    eligible_total += data['raw_share']
            
            if eligible_ids and eligible_total > 0:
                remainder = Decimal(1) - total_share
                # Distribute remainder proportional to their current shares
                for hid in eligible_ids:
                    ratio = self.shares[hid]['raw_share'] / eligible_total
                    add_amt = remainder * ratio
                    self.shares[hid]['raw_share'] += add_amt
                    self.shares[hid]['fraction'] += " + مع الرد"
            else:
                # If only spouses act, or no one eligible?
                # If only spouses, technically Byte al-Mal, or in modern law often Radd to spouses.
                # Implementing Radd to spouses if no one else exists.
                if eligible_total == 0 and self.shares:
                    for hid in self.shares:
                        ratio = self.shares[hid]['raw_share'] / total_share
                        self.shares[hid]['raw_share'] += (Decimal(1) - total_share) * ratio
                        self.shares[hid]['fraction'] += " + مع الرد"

# def finalize_values(self):
    #     for hid in self.shares:
    #         raw = self.shares[hid]['raw_share']
    #         self.shares[hid]['percentage'] = raw * 100
    #         self.shares[hid]['value'] = (raw * self.net_estate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
    #         # Sanity format of fraction for display if it became complex float
    #         # Keeping the string clean if possible, otherwise just use logic description
    from decimal import Decimal, ROUND_HALF_UP

    def finalize_values(self):
        for hid in self.shares:
            raw = self.shares[hid]['raw_share']
            percentage = raw * 100
        
            # حساب قيمة النصيب من التركة
            value = (raw * self.net_estate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
            # تحويل إلى float للحفاظ على النقطة كنقطة عشرية
            self.shares[hid]['percentage'] = float(percentage)
            self.shares[hid]['value'] = float(value)
        
        # fraction يبقى كما هو (string) بدون أي تغيير
        # raw_share يبقى Decimal داخليًا
