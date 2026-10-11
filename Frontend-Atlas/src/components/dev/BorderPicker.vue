<template>
  <div class="space-y-2">
    <p v-if="isLoadingCountries" class="text-[11px] text-base-content/60">
      <span class="loading loading-spinner loading-xs align-middle mr-1" />
      Lecture des fichiers de frontières… (quelques secondes la première fois)
    </p>
    <div
      v-else-if="countries.length === 0 && !error"
      role="alert"
      class="alert alert-warning alert-soft text-xs py-2"
    >
      <span>
        Aucun fichier de frontières. Lancez
        <code>scripts/fetch_natural_earth_borders.py</code>, ou déposez des
        fichiers admin-0 / admin-1 dans <code>app/geojson/borders/</code>.
      </span>
    </div>

    <template v-else>
      <!-- Level 1: the country. A combobox: type to filter, the list floats
           over what is below it and scrolls. -->
      <div class="dropdown w-full" :class="{ 'dropdown-open': isCountryListOpen }">
        <label class="input input-sm w-full flex items-center gap-2 py-0">
          <MagnifyingGlassIcon class="h-4 w-4 opacity-50" />
          <input
            ref="countryInput"
            v-model="countryQuery"
            type="text"
            class="grow"
            placeholder="Pays (ex. Canada, Italie)"
            role="combobox"
            :aria-expanded="isCountryListOpen"
            @focus="openCountryList"
            @blur="isCountryListOpen = false"
            @input="onCountryInput"
            @keydown.down.prevent="moveHighlight(1)"
            @keydown.up.prevent="moveHighlight(-1)"
            @keydown.enter.prevent="pickHighlighted"
            @keydown.esc.prevent="closeCountryList"
          />
          <button
            v-if="countryCode"
            type="button"
            class="btn btn-ghost btn-xs btn-circle"
            title="Changer de pays"
            @mousedown.prevent="clearCountry"
          >
            ✕
          </button>
        </label>
        <ul
          v-if="isCountryListOpen"
          ref="countryList"
          class="dropdown-content menu menu-sm bg-base-100 rounded-box border border-base-300 shadow-lg z-[1000] mt-1 w-full max-h-80 overflow-y-auto flex-nowrap p-1"
          role="listbox"
        >
          <li v-if="filteredCountries.length === 0" class="menu-disabled">
            <span>Aucun pays ne correspond.</span>
          </li>
          <li v-for="(c, i) in filteredCountries" :key="c.code" :data-index="i">
            <!-- mousedown, not click: picking must happen before the input blurs
                 and closes the list. -->
            <button
              type="button"
              class="flex justify-between gap-2"
              :class="{ 'menu-active': i === highlighted }"
              role="option"
              :aria-selected="c.code === countryCode"
              @mousedown.prevent="pickCountry(c)"
              @mouseenter="highlighted = i"
            >
              <span class="truncate">{{ c.name }}</span>
              <span class="badge badge-ghost badge-xs shrink-0">
                {{ c.regionCount ? `${c.regionCount} régions` : "pays" }}
              </span>
            </button>
          </li>
        </ul>
      </div>

      <template v-if="country">
        <button
          v-if="country.hasOutline"
          type="button"
          class="btn btn-xs btn-outline w-full"
          :disabled="isLoadingZone"
          @click="loadZone(null)"
        >
          Charger le pays entier ({{ country.name }})
        </button>

        <!-- Level 2: its regions, grouped when the file says how -->
        <template v-if="country.regionCount > 0">
          <p v-if="isLoadingRegions" class="text-[11px] text-base-content/60">
            Chargement des régions…
          </p>
          <template v-else>
            <label class="input input-sm w-full flex items-center gap-2 py-0">
              <MagnifyingGlassIcon class="h-4 w-4 opacity-50" />
              <input
                v-model="regionFilter"
                type="text"
                class="grow"
                placeholder="Filtrer les régions"
              />
            </label>
            <!-- Grouped when the file says how (Italy's provinces by region):
                 ticking a group ticks all its units. -->
            <ul
              class="menu menu-xs w-full max-h-72 overflow-y-auto flex-nowrap bg-base-100 border border-base-300 rounded-box"
            >
              <template v-for="group in groupedRegions" :key="group.name ?? '-'">
                <li v-if="group.name">
                  <label
                    class="font-semibold"
                    :title="`Sélectionner les ${group.regions.length} unités de ${group.name}`"
                  >
                    <input
                      type="checkbox"
                      class="checkbox checkbox-xs"
                      :checked="isGroupSelected(group)"
                      :indeterminate.prop="isGroupPartial(group)"
                      @change="toggleGroup(group, ($event.target as HTMLInputElement).checked)"
                    />
                    {{ group.name }}
                    <span class="font-normal text-base-content/50">({{ group.regions.length }})</span>
                  </label>
                </li>
                <li v-for="r in group.regions" :key="r.id" :class="{ 'pl-4': group.name }">
                  <label>
                    <input
                      type="checkbox"
                      class="checkbox checkbox-xs"
                      :checked="selected.has(r.id)"
                      @change="toggleRegion(r.id, ($event.target as HTMLInputElement).checked)"
                    />
                    {{ r.name }}
                  </label>
                </li>
              </template>
            </ul>
            <button
              type="button"
              class="btn btn-xs btn-primary w-full"
              :disabled="selected.size === 0 || isLoadingZone"
              @click="loadZone([...selected])"
            >
              Charger {{ selected.size }} région{{ selected.size > 1 ? "s" : "" }}
              <span v-if="selected.size > 1">(fusionnées en une zone)</span>
            </button>
          </template>
        </template>
      </template>
    </template>

    <p v-if="isLoadingZone" class="text-[11px] text-base-content/60">
      <span class="loading loading-spinner loading-xs align-middle mr-1" />
      Chargement de la zone…
    </p>
    <div v-if="error" role="alert" class="alert alert-error alert-soft text-xs py-2">
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { MagnifyingGlassIcon } from "@heroicons/vue/24/outline";
import { useBorders } from "../../composables/useBorders";
import type { BorderCountry, BorderRegion, LoadedBorderZone } from "../../typescript/devTest";

type RegionGroup = { name: string | null; regions: BorderRegion[] };

const emit = defineEmits<{
  // One zone: a whole country, or the union of the selected regions.
  (e: "loaded", zone: LoadedBorderZone): void;
}>();

const borders = useBorders();
const countries = ref<BorderCountry[]>([]);
// What the country field shows: the filter while typing, the chosen country's
// name once picked.
const countryQuery = ref("");
const countryCode = ref<string | null>(null);
const isCountryListOpen = ref(false);
const highlighted = ref(0);
const countryInput = ref<HTMLInputElement | null>(null);
const countryList = ref<HTMLUListElement | null>(null);
const regions = ref<BorderRegion[]>([]);
const regionFilter = ref("");
const selected = ref<Set<string>>(new Set());
const isLoadingCountries = ref(false);
const isLoadingRegions = ref(false);
const isLoadingZone = ref(false);
const error = ref<string | null>(null);

// Accents and case ignored: "quebec" finds Québec.
function normalise(text: string): string {
  return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

const country = computed(
  () => countries.value.find((c) => c.code === countryCode.value) ?? null,
);

// The chosen country's name in the field is not a filter: show the whole list.
const filteredCountries = computed(() => {
  const query = countryQuery.value.trim();
  if (!query || query === country.value?.name) return countries.value;
  const needle = normalise(query);
  return countries.value.filter(
    (c) => normalise(c.name).includes(needle) || c.code.toLowerCase().includes(needle),
  );
});

function openCountryList() {
  isCountryListOpen.value = true;
  const selectedIndex = filteredCountries.value.findIndex((c) => c.code === countryCode.value);
  highlighted.value = Math.max(selectedIndex, 0);
  scrollHighlightedIntoView();
}

function closeCountryList() {
  isCountryListOpen.value = false;
  countryInput.value?.blur();
}

function onCountryInput() {
  isCountryListOpen.value = true;
  highlighted.value = 0;
}

function moveHighlight(step: number) {
  if (!isCountryListOpen.value) {
    openCountryList();
    return;
  }
  const count = filteredCountries.value.length;
  if (count === 0) return;
  highlighted.value = (highlighted.value + step + count) % count;
  scrollHighlightedIntoView();
}

function scrollHighlightedIntoView() {
  nextTick(() => {
    countryList.value
      ?.querySelector(`[data-index="${highlighted.value}"]`)
      ?.scrollIntoView({ block: "nearest" });
  });
}

function pickHighlighted() {
  const c = filteredCountries.value[highlighted.value];
  if (c) pickCountry(c);
}

function pickCountry(c: BorderCountry) {
  countryCode.value = c.code;
  countryQuery.value = c.name;
  closeCountryList();
}

function clearCountry() {
  countryCode.value = null;
  countryQuery.value = "";
  countryInput.value?.focus();
}

const groupedRegions = computed<RegionGroup[]>(() => {
  const needle = normalise(regionFilter.value.trim());
  const groups = new Map<string | null, BorderRegion[]>();
  for (const r of regions.value) {
    if (needle && !normalise(r.name).includes(needle) && !normalise(r.group ?? "").includes(needle)) {
      continue;
    }
    const list = groups.get(r.group) ?? [];
    list.push(r);
    groups.set(r.group, list);
  }
  return [...groups.entries()].map(([name, list]) => ({ name, regions: list }));
});

function isGroupSelected(group: RegionGroup): boolean {
  return group.regions.every((r) => selected.value.has(r.id));
}

function isGroupPartial(group: RegionGroup): boolean {
  return !isGroupSelected(group) && group.regions.some((r) => selected.value.has(r.id));
}

function toggleRegion(id: string, checked: boolean) {
  const next = new Set(selected.value);
  if (checked) next.add(id);
  else next.delete(id);
  selected.value = next;
}

function toggleGroup(group: RegionGroup, checked: boolean) {
  const next = new Set(selected.value);
  for (const r of group.regions) {
    if (checked) next.add(r.id);
    else next.delete(r.id);
  }
  selected.value = next;
}

async function loadCountries() {
  isLoadingCountries.value = true;
  error.value = null;
  const res = await borders.listCountries();
  if (res.success) countries.value = res.data;
  else error.value = res.error;
  isLoadingCountries.value = false;
}

watch(countryCode, async (code) => {
  regions.value = [];
  selected.value = new Set();
  regionFilter.value = "";
  if (!code || !country.value?.regionCount) return;
  isLoadingRegions.value = true;
  error.value = null;
  const res = await borders.listRegions(code);
  if (res.success) regions.value = res.data;
  else error.value = res.error;
  isLoadingRegions.value = false;
});

async function loadZone(regionIds: string[] | null) {
  if (!countryCode.value) return;
  isLoadingZone.value = true;
  error.value = null;
  const res = await borders.loadZone(countryCode.value, regionIds);
  if (res.success) emit("loaded", res.data);
  else error.value = res.error;
  isLoadingZone.value = false;
}

onMounted(loadCountries);
</script>
