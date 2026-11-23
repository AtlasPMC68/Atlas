<template>
  <div class="flex h-full min-h-0 flex-col" data-testid="feature-visibility-controls">
    <div class="tabs tabs-boxed bg-base-200 gap-2 p-1.5">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
        :aria-selected="activeGroup?.type === group.type"
        :data-testid="`feature-tab-${group.type}`"
        class="tab flex-1 p-0"
        :title="`${group.label}`"
        @click="activeGroupType = group.type"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>

    <!-- Liste des éléments avec contrôle de visibilité -->
    <div class="px-1 flex flex-1 flex-col min-h-0">
      <div
        class="card flex flex-1 flex-col gap-4 min-h-0 overflow-y-auto scroll-stable"
      >
        <div class="flex items-center justify-between">
          <label
            class="label cursor-pointer justify-start gap-2 flex-1 min-w-0"
          >
            <input
              type="checkbox"
              :checked="isAnyVisible"
              @change="toggleActiveGroup(!isAnyVisible)"
              class="checkbox checkbox-sm checkbox-primary"
            />
            <span class="text-sm font-bold text-gray-900 truncate">
              {{ activeGroup?.label }}
            </span>
          </label>
        </div>
        <div class="divider m-0 h-0"></div>

        <!-- Validate extracted texts button -->
        <div
          v-if="activeGroup?.type === 'point' && validationFeaturesByMap.length > 0"
          class="flex flex-col gap-2 p-2 bg-primary-50 border border-primary-200 rounded-lg"
        >
          <span class="text-xs font-bold flex items-center gap-1.5">
            <DocumentCheckIcon class="w-4 h-4 text-primary-600" />
            Textes non reconnus
          </span>
          <button
            type="button"
            class="btn btn-primary btn-xs w-full"
            @click="openMapSelectionOrValidate"
          >
            Examiner les rejets
          </button>
        </div>

        <div class="flex flex-col gap-2">
          <template v-if="featuresByMap.length > 0">
            <div
              v-for="mapGroup in featuresByMap"
              :key="mapGroup.id ?? 'general'"
              class="flex flex-col gap-2"
            >
              <div
                class="flex items-center justify-between rounded-lg px-2 py-1 bg-gray-100 hover:bg-gray-200/80 border border-gray-300 group transition-colors cursor-pointer"
                :class="{ 'ring-2 ring-primary border-primary bg-primary/5': props.activeMapId && mapGroup.id === props.activeMapId }"
                @click="mapGroup.id !== null && emit('select-map', mapGroup.id)"
                @dblclick="mapGroup.id !== null && emit('edit-map', mapGroup.id)"
              >
                <div class="flex items-center gap-1.5 flex-1 min-w-0">
                  <button
                    type="button"
                    class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-gray-500 hover:text-gray-800 hover:bg-gray-300/60 transition-colors focus:outline-none"
                    @click.stop="toggleMapCollapse(mapGroup.id)"
                    :title="isMapCollapsed(mapGroup.id) ? `Développer ${mapGroup.title}` : `Réduire ${mapGroup.title}`"
                    :aria-label="isMapCollapsed(mapGroup.id) ? `Développer ${mapGroup.title}` : `Réduire ${mapGroup.title}`"
                  >
                    <ChevronDownIcon
                      class="w-4 h-4 transition-transform duration-200"
                      :class="{ '-rotate-90': isMapCollapsed(mapGroup.id) }"
                    />
                  </button>
                  <label
                    class="label cursor-pointer justify-start gap-2 flex-1 min-w-0 p-0"
                    @click.stop
                  >
                    <input
                      type="checkbox"
                      :checked="isMapGroupAnyVisible(mapGroup.id)"
                      @change="
                        toggleMapGroup(
                          mapGroup.id,
                          !isMapGroupAnyVisible(mapGroup.id),
                        )
                      "
                      class="checkbox checkbox-sm checkbox-primary shrink-0"
                    />
                    <button
                      v-if="mapGroup.id !== null"
                      type="button"
                      class="text-sm font-bold text-gray-900 truncate text-left hover:text-primary flex-1 min-w-0"
                      :title="`${mapGroup.title} (clic pour sélectionner, double-clic pour modifier)`"
                      :data-testid="`map-title-btn-${mapGroup.id}`"
                      @click.stop="emit('select-map', mapGroup.id)"
                      @dblclick.stop="emit('edit-map', mapGroup.id)"
                    >
                      {{ mapGroup.title }}
                    </button>
                    <span
                      v-else
                      class="text-sm font-bold text-gray-900 truncate flex-1 min-w-0"
                      title="Éléments qui appartiennent à toutes les cartes"
                    >
                      {{ mapGroup.title }}
                    </span>
                  </label>
                </div>
                <div class="flex items-center gap-0.5 shrink-0 ml-auto -mr-1.5" v-if="mapGroup.id !== null">
                  <button
                    type="button"
                    class="icon-action-btn-sm"
                    :aria-label="`Modifier le nom et la période de ${mapGroup.title}`"
                    title="Modifier le nom et la période"
                    @click.stop="emit('edit-map', mapGroup.id)"
                  >
                    <PencilSquareIcon class="w-3.5 h-3.5 text-gray-500 hover:text-primary" />
                  </button>
                  <button
                    type="button"
                    class="icon-action-btn-sm"
                    @click="showDeleteMapDialog(mapGroup.id, mapGroup.title)"
                    title="Supprimer la carte"
                    aria-label="Supprimer la carte"
                  >
                    <TrashIcon class="w-3.5 h-3.5 text-error hover:text-error/80" />
                  </button>
                </div>
              </div>
              <div v-if="!isMapCollapsed(mapGroup.id)" class="flex flex-col gap-1 pl-6">
                <div
                  v-for="feature in mapGroup.features"
                  :key="feature.id"
                  :data-feature-item-id="String(feature.id)"
                  class="flex w-full flex-row items-center justify-between gap-1 rounded-lg px-2 py-1 transition-all cursor-pointer select-none"
                  :class="[
                    isFeatureSelected(feature.id)
                      ? 'border-2 border-primary bg-primary/10 font-semibold shadow-sm'
                      : 'border-2 border-transparent hover:bg-base-200/60'
                  ]"
                  @click="onFeatureItemClick(feature, $event)"
                  @dblclick.prevent.stop="onFeatureItemDblClick(feature, $event)"
                >
                  <div class="flex items-center gap-1.5 flex-1 min-w-0 py-0 pl-0">
                    <span
                      v-if="!feature.properties?.name?.trim()"
                      class="text-error font-extrabold text-sm leading-none shrink-0"
                      title="Nom manquant"
                    >
                      !
                    </span>
                    <input
                      type="checkbox"
                      :checked="featureVisibility.get(feature.id) !== false"
                      @click.stop
                      @change="
                        $emit(
                          'toggle-feature',
                          feature.id,
                          ($event.target as HTMLInputElement).checked,
                        )
                      "
                      class="checkbox checkbox-xs checkbox-primary shrink-0"
                    />
                    <span
                      class="label-text text-sm truncate flex-1 min-w-0 select-none"
                      :title="feature.properties?.name?.trim() || 'Nom manquant'"
                      @dblclick.prevent.stop="onFeatureItemDblClick(feature)"
                    >
                      <span
                        class="truncate block"
                        :class="!feature.properties?.name?.trim() ? 'text-error font-medium' : ''"
                      >
                        {{ feature.properties?.name?.trim() || "Nom manquant" }}
                      </span>
                    </span>
                    <span
                      v-if="feature.properties?.startYear != null || feature.properties?.endYear != null"
                      class="badge badge-ghost badge-xs font-normal opacity-70 shrink-0 ml-auto"
                    >
                      {{ feature.properties.startYear }}{{ feature.properties.endYear && feature.properties.endYear !== feature.properties.startYear ? ' - ' + feature.properties.endYear : '' }}
                    </span>
                    <span
                      v-else-if="getFeatureMapIds(feature).length > 1"
                      class="badge badge-info badge-outline badge-xs font-semibold shrink-0 ml-auto"
                      :title="`Partagé sur ${getFeatureMapIds(feature).length} cartes`"
                    >
                      {{ getFeatureMapIds(feature).length }} cartes
                    </span>
                  </div>
                  <div class="flex items-center gap-0.5 shrink-0 ml-auto -mr-1">
                    <button
                      type="button"
                      class="icon-action-btn-sm"
                      @click.stop="showEditFeatureDialog(feature)"
                      title="Modifier l'élément"
                      aria-label="Modifier l'élément"
                    >
                      <PencilSquareIcon
                        class="w-3.5 h-3.5 text-gray-500 hover:text-gray-800"
                      />
                    </button>
                    <button
                      type="button"
                      class="icon-action-btn-sm"
                      @click.stop="showDeleteFeatureDialog(feature)"
                      title="Supprimer l'élément"
                      aria-label="Supprimer l'élément"
                    >
                      <TrashIcon
                        class="w-3.5 h-3.5 text-red-500 hover:text-red-800"
                      />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="flex text-sm opacity-60">
            Aucun élément à afficher
          </div>
        </div>
      </div>
    </div>

    <div class="px-3 py-1.5 flex flex-col gap-1.5">
      <div class="divider m-0"></div>
      <template v-if="!props.isDevTestCreation">
        <div class="flex flex-col gap-1.5">
          <button
            class="btn btn-primary btn-sm w-full font-bold"
            @click="$emit('add-map')"
          >
            <PlusIcon class="w-5 h-5" />
            Ajouter une carte
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm w-full font-bold"
            data-testid="sidebar-duplicate-map-button"
            title="Dupliquer entièrement une carte"
            @click="$emit('duplicate-map')"
          >
            <DocumentDuplicateIcon class="w-4 h-4" />
            Dupliquer une carte
          </button>
        </div>

        <div class="flex gap-2 items-center">
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('open-add-image-feature-dialog')"
          >
            <PlusIcon class="w-5 h-5" />
            Image
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('save-map')"
          >
            <FolderArrowDownIcon class="w-5 h-5" />
            Enregistrer
          </button>
        </div>
      </template>
      <div class="flex gap-2 items-center">
        <button
          @click="toggleAll(true)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout afficher
        </button>
        <button
          @click="toggleAll(false)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout masquer
        </button>
      </div>
    </div>
  </div>

  <!-- Modale d'édition d'élément uniformisée -->
  <dialog ref="editFeatureDialogRef" class="modal" v-if="featureToEdit">
    <div class="modal-box w-11/12 max-w-6xl flex flex-col gap-4">
      <h3 class="text-lg font-bold truncate">
        Modification {{ editModalTypeLabel }}
        <span :class="isEditNameMissing ? 'text-error font-medium' : ''">
          {{ editModalNameText }}
        </span>
      </h3>

      <fieldset class="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-6 items-start">
        <!-- Colonne gauche : Informations générales, Texte et Style géométrique unifié -->
        <div class="flex flex-col gap-4 min-w-0">
          <div class="flex flex-col gap-1.5">
            <span class="section-title">
              Informations générales
            </span>

            <div
              class="grid grid-cols-1 gap-3 items-start w-full"
              :class="isTextElement ? 'sm:grid-cols-2' : 'grid-cols-1'"
            >
              <div class="flex flex-col gap-1 min-w-0">
                <label class="field-label" for="edit-feature-name">
                  Nom de l'élément
                </label>

                <template v-if="isTextElement">
                  <textarea
                    id="edit-feature-name"
                    ref="labelTextareaRef"
                    v-model="editDraft.name"
                    rows="2"
                    class="textarea textarea-bordered w-full bg-base-100 text-sm leading-snug resize-y"
                    :class="isEditNameMissing ? 'border-error ring-1 ring-error' : 'border-gray-400'"
                    placeholder="Nom de l'élément"
                    required
                    @input="onNameInput"
                  ></textarea>
                  <span class="field-hint">
                    Vous pouvez le mettre sur plusieurs lignes en appuyant sur Entrée.
                  </span>
                </template>

                <input
                  v-else
                  id="edit-feature-name"
                  v-model="editDraft.name"
                  type="text"
                  class="input input-bordered w-full text-sm"
                  :class="isEditNameMissing ? 'border-error ring-1 ring-error' : 'border-gray-400'"
                  placeholder="Nom de l'élément"
                  required
                  @input="onNameInput"
                />
              </div>

              <div v-if="isTextElement" class="flex flex-col gap-1 min-w-0">
                <span class="field-label">
                  Aperçu
                </span>
                <div class="preview-frame p-2">
                  <div
                    class="preview-box px-2.5 py-1.5 min-h-[42px]"
                    :style="editTextStyle"
                  >
                    <span
                      v-if="isEditingPoint"
                      class="inline-block h-3 w-3 rounded-full shrink-0 border border-base-content"
                      :style="{ backgroundColor: pointPreviewFillColor }"
                    ></span>
                    <span class="whitespace-pre-line break-words">
                      {{ editDraft.labelText || editDraft.name || "Exemple de texte" }}
                    </span>
                  </div>
                </div>
                <span
                  v-if="isPreviewClamped"
                  class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1 mt-1"
                  data-testid="preview-limit-notice"
                >
                  L'aperçu est plafonné pour tenir dans la fenêtre.
                </span>
              </div>
            </div>
          </div>

          <!-- Réglages du texte -->
          <div v-if="isTextElement" class="editor-section">
            <span class="section-title">
              Réglages du texte
            </span>

            <div class="flex flex-col gap-1">
              <label class="field-label">Type de mot</label>
              <div class="flex flex-row items-center gap-2 w-full">
                <select
                  v-model="editDraft.labelStyleSelection"
                  data-testid="word-type-select"
                  class="select select-bordered flex-1 min-w-0 h-[50px] text-sm"
                  @change="onLabelStyleSelectionChange"
                >
                  <option
                    v-for="style in availableCustomLabelStyles"
                    :key="style.id"
                    :value="`custom:${style.id}`"
                    :style="getCustomStyleObject(style)"
                    class="text-sm"
                  >
                    {{ style.name }}
                  </option>
                  <option
                    v-for="(_, typeKey) in WORD_TYPE_STYLES"
                    :key="typeKey"
                    :value="typeKey"
                    :style="getWordTypeOptionStyle(typeKey)"
                    class="text-sm"
                  >
                    {{ getWordTypeOptionLabel(typeKey) }}
                  </option>
                </select>
                <button
                  type="button"
                  class="modal-secondary-btn h-[50px]"
                  data-testid="manage-custom-label-styles"
                  @click="labelStyleManagerRef?.open()"
                >
                  Personnaliser
                </button>
              </div>
            </div>

            <div
              v-if="!editDraft.customLabelStyleId"
              class="flex flex-col gap-1 w-full"
            >
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
                <div class="setting-card">
                  <label class="setting-card-label" for="edit-feature-text-color">
                    Couleur texte
                  </label>
                  <input
                    id="edit-feature-text-color"
                    v-model="editDraft.textColorHex"
                    data-testid="text-color-input"
                    type="color"
                    class="setting-color-input"
                  />
                </div>

                <div
                  class="setting-card"
                  :class="{ 'border-error': isTextSizeOverMax }"
                >
                  <label class="setting-card-label" for="edit-feature-text-size">
                    Taille (px)
                  </label>
                  <input
                    id="edit-feature-text-size"
                    v-model.number="editDraft.textSizePx"
                    data-testid="text-size-input"
                    type="number"
                    :min="MIN_TEXT_SIZE_PX"
                    :max="MAX_TEXT_SIZE_PX"
                    step="1"
                    class="setting-number-input"
                    @change="onTextSizeChange"
                  />
                </div>
              </div>

              <span
                v-if="isTextSizeOverMax"
                class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1 mt-1"
                data-testid="text-size-max-warning"
              >
                La taille maximale autorisée est de {{ MAX_TEXT_SIZE_PX }} px (la valeur a été plafonnée).
              </span>
            </div>
          </div>

          <!-- Réglages géométriques unifiés (Point ou Forme / Zone / Ligne) -->
          <div v-if="hasGeometryControls" class="editor-section">
            <div class="flex items-baseline justify-between gap-2">
              <span class="section-title">
                {{ geometrySectionTitle }}
              </span>
              <span class="field-hint">
                {{ geometrySectionHint }}
              </span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 w-full">
              <div class="setting-card">
                <label class="setting-card-label" for="edit-feature-fill-color">
                  Fond
                </label>
                <input
                  id="edit-feature-fill-color"
                  v-model="editDraft.colorHex"
                  data-testid="color-input"
                  type="color"
                  class="setting-color-input"
                />
              </div>

              <div class="setting-card">
                <label class="setting-card-label" for="edit-feature-stroke-color">
                  Contour
                </label>
                <input
                  id="edit-feature-stroke-color"
                  v-model="editDraft.strokeColorHex"
                  data-testid="point-stroke-color-input"
                  type="color"
                  class="setting-color-input"
                />
              </div>

              <!-- Aperçu séparé en deux colonnes : texte à gauche, rendu agrandi à droite -->
              <div
                class="setting-preview-card"
                data-testid="point-preview-container"
              >
                <span class="setting-card-label px-3">
                  Aperçu
                </span>
                <div class="h-full flex items-center justify-center border-l border-gray-300 bg-base-100 px-2 py-1">
                  <svg width="36" height="36" viewBox="0 0 40 40" class="overflow-visible">
                    <circle
                      v-if="isEditingPoint"
                      cx="20"
                      cy="20"
                      r="14"
                      :fill="pointPreviewFillColor"
                      :fill-opacity="pointPreviewFillOpacity"
                      :stroke="pointPreviewStrokeColor"
                      :stroke-width="pointPreviewStrokeWidth"
                      :stroke-opacity="pointPreviewStrokeOpacity"
                    />
                    <rect
                      v-else
                      x="3"
                      y="5"
                      width="34"
                      height="30"
                      rx="5"
                      :fill="pointPreviewFillColor"
                      :fill-opacity="pointPreviewFillOpacity"
                      :stroke="pointPreviewStrokeColor"
                      :stroke-width="pointPreviewStrokeWidth"
                      :stroke-opacity="pointPreviewStrokeOpacity"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 w-full">
              <div class="setting-card">
                <label
                  class="setting-card-label"
                  for="edit-fill-opacity"
                  title="Opacité du fond (0 à 1)"
                >
                  Opacité fond
                </label>
                <input
                  id="edit-fill-opacity"
                  v-model.number="editDraft.fillOpacity"
                  data-testid="fill-opacity-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input"
                  @change="editDraft.fillOpacity = normalizeOpacity(editDraft.fillOpacity)"
                />
              </div>

              <div class="setting-card">
                <label
                  class="setting-card-label"
                  for="edit-stroke-opacity"
                  title="Opacité du contour (0 à 1)"
                >
                  Opacité contour
                </label>
                <input
                  id="edit-stroke-opacity"
                  v-model.number="editDraft.strokeOpacity"
                  data-testid="stroke-opacity-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input"
                  @change="editDraft.strokeOpacity = normalizeOpacity(editDraft.strokeOpacity)"
                />
              </div>

              <div class="setting-card">
                <label
                  class="setting-card-label"
                  for="edit-stroke-width"
                  title="Épaisseur du contour en pixels"
                >
                  Épaisseur contour
                </label>
                <input
                  id="edit-stroke-width"
                  v-model.number="editDraft.strokeWidth"
                  data-testid="stroke-width-input"
                  type="number"
                  min="0"
                  :max="MAX_STROKE_WIDTH_PX"
                  class="setting-number-input"
                  @change="editDraft.strokeWidth = normalizeStrokeWidth(editDraft.strokeWidth)"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Colonne droite : Cartes associées & Dates -->
        <div class="flex flex-col gap-3 min-w-0">
          <div
            v-if="props.mapPeriods && props.mapPeriods.length > 0"
            class="flex flex-col gap-1.5 min-w-0"
            data-testid="map-assignment-section"
          >
            <div class="flex items-center justify-between">
              <label class="section-title">
                Cartes associées
              </label>
              <button
                type="button"
                class="btn btn-ghost btn-xs text-primary font-semibold hover:bg-primary/10 disabled:opacity-40 disabled:cursor-not-allowed"
                :disabled="hasCustomDate"
                @click="toggleSelectAllMaps"
              >
                {{ areAllMapsSelected ? "Tout désélectionner" : "Tout sélectionner" }}
              </button>
            </div>
            <div
              v-if="editDraft.selectedMapIds && editDraft.selectedMapIds.length > 1"
              class="alert alert-info py-1.5 px-2.5 text-xs rounded-lg flex items-center gap-2 mb-1"
            >
              <InformationCircleIcon class="w-4 h-4 shrink-0 text-info" />
              <span>Cet élément est partagé sur {{ editDraft.selectedMapIds.length }} cartes. Toute modification sera synchronisée sur l'ensemble de ces cartes.</span>
            </div>
            <div class="flex flex-col gap-1 max-h-32 overflow-y-auto border border-gray-400 rounded-lg p-2 bg-base-100">
              <label
                v-for="period in props.mapPeriods"
                :key="period.id"
                class="flex items-center gap-2 rounded px-1.5 py-0.5"
                :class="hasCustomDate ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:bg-base-200/50'"
              >
                <input
                  type="checkbox"
                  :value="period.id"
                  v-model="editDraft.selectedMapIds"
                  class="checkbox checkbox-xs checkbox-primary"
                  :data-testid="`map-checkbox-${period.id}`"
                  :disabled="hasCustomDate"
                />
                <span class="text-sm truncate">{{ period.title }}</span>
              </label>
            </div>
            <span
              v-if="hasCustomDate"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1 mt-1"
            >
              Période personnalisée active : aucune carte ne peut être associée. Effacez les dates pour sélectionner une carte.
            </span>
            <span v-else class="field-hint">
              Si aucune carte n'est sélectionnée, l'élément reste dans « Éléments généraux ».
            </span>
          </div>

          <div
            class="editor-section-compact"
            data-testid="feature-years-section"
          >
            <div class="flex items-center gap-1.5">
              <label class="section-title">
                Période personnalisée
              </label>
              <div
                class="tooltip tooltip-light tooltip-bottom md:tooltip-left cursor-pointer"
                data-tip="Définit une période d'apparition propre à cet élément sur la ligne du temps (élément général sans carte associée)."
              >
                <div class="w-4 h-4 rounded-full bg-base-300 text-base-content opacity-80 flex items-center justify-center text-[10px] font-bold hover:bg-primary hover:text-primary-content transition-colors">
                  !
                </div>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="field-label">Année de début</label>
                <input
                  v-model.number="editDraft.startYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input input-bordered input-sm w-full text-sm"
                  placeholder="Ex: 1600"
                  data-testid="feature-start-year-input"
                  @input="onFeatureStartYearInput"
                />
              </div>
              <div>
                <label class="field-label">Année de fin</label>
                <input
                  v-model.number="editDraft.endYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input input-bordered input-sm w-full text-sm"
                  placeholder="Ex: 1650"
                  data-testid="feature-end-year-input"
                  @input="onFeatureEndYearInput"
                />
              </div>
            </div>
          </div>
        </div>
      </fieldset>

      <div class="modal-action mt-2">
        <button
          class="modal-secondary-btn w-32"
          :disabled="isEditing"
          @click="editFeatureDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary rounded-lg w-32"
          :disabled="isEditing"
          @click="onEditFeature"
        >
          <span
            v-if="isEditing"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Modifier</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isEditing">close</button>
    </form>
  </dialog>

  <CustomLabelStyleManager
    ref="labelStyleManagerRef"
    :styles="availableCustomLabelStyles"
    @save="onSaveCustomLabelStyles"
  />

  <!-- Delete map confirmation dialog -->
  <dialog ref="deleteMapDialogRef" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold">Supprimer la carte</h3>
      <p class="py-4">
        Êtes-vous sûr de vouloir supprimer la carte
        <span class="font-semibold">{{ mapToDeleteTitle }}</span> ainsi que tous ses éléments ?
        Cette action est irréversible.
      </p>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isDeletingMap"
          @click="deleteMapDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-error"
          :disabled="isDeletingMap"
          @click="onDeleteMap"
        >
          <span
            v-if="isDeletingMap"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Supprimer</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDeletingMap">close</button>
    </form>
  </dialog>

  <!-- Delete feature confirmation dialog -->
  <DeleteFeatureDialog
    ref="deleteFeatureDialogRef"
    :features="props.features"
    :map-periods="props.mapPeriods"
    :active-map-id="props.activeMapId"
    :is-deleting="isDeletingFeature"
    @delete-features="onDeleteFeaturesConfirmed"
    @remove-from-maps="onRemoveFromMapsConfirmed"
  />

  <!-- Map selection dialog for text validation -->
  <dialog ref="selectMapValidationDialogRef" data-testid="select-map-validation-dialog" class="modal z-[2500]">
    <div class="modal-box max-w-sm">
      <h3 class="text-lg font-bold flex items-center gap-2">
        <DocumentCheckIcon class="w-5 h-5 text-primary-600" />
        Choisir la carte à examiner
      </h3>
      <p class="text-sm text-base-content opacity-70 mt-1 mb-4">
        Sélectionnez la carte dont vous souhaitez examiner et valider les textes rejetés :
      </p>
      <div class="flex flex-col gap-2">
        <button
          v-for="group in validationFeaturesByMap"
          :key="group.id ?? 'general'"
          type="button"
          class="btn btn-outline btn-sm justify-between text-left"
          @click="confirmMapValidation(group.id)"
        >
          <span class="font-medium truncate">{{ group.title }}</span>
          <span class="text-xs font-normal opacity-60">Ouvrir →</span>
        </button>
      </div>
      <div class="modal-action mt-4">
        <button
          type="button"
          class="btn"
          @click="selectMapValidationDialogRef?.close()"
        >
          Annuler
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { Component } from "vue";
import type { CSSProperties } from "vue";
import {
  ChatBubbleLeftEllipsisIcon,
  ChevronDownIcon,
  DocumentCheckIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  MapIcon,
  PencilSquareIcon,
  PhotoIcon,
  Square2StackIcon,
  TrashIcon,
} from "@heroicons/vue/24/outline";
import {
  type Feature,
  type FeatureVisibilityGroup,
  type FeatureVisibilityGroupType,
} from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import type { CustomLabelStyle, LabelStyle } from "../utils/labelPresentation";
import {
  MAX_TEXT_SIZE_PX,
  MIN_TEXT_SIZE_PX,
  normalizeTextSizePx,
  MAX_PREVIEW_FONT_SIZE_PX,
  getLabelStylePreviewCss,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  getCustomStyleObject,
} from "../utils/labelPresentation";
import CustomLabelStyleManager from "./CustomLabelStyleManager.vue";
import DeleteFeatureDialog from "./DeleteFeatureDialog.vue";
import { getFeatureMapId, getFeatureMapIds, getMapElementType } from "../utils/featureHelpers";
import {
  WORD_TYPE_STYLES,
  WORD_TYPE_TAXONOMY,
  isTextFeature,
  formatWordText,
} from "../utils/wordStyles";
import {
  prepareFeatureForEdit,
  coerceEditedFeature,
  createFeaturesForSelectedMaps,
  getWordTypePreviewStyle,
  getDefaultTextSizePx,
  normalizeOpacity,
  normalizeStrokeWidth,
  MAX_STROKE_WIDTH_PX,
  type FeatureEditSubmitPayload,
} from "../utils/featureTextEditing";
import { rgbToHex } from "../utils/utils";
import { syncEndFromStart } from "../utils/dateUtils";
import {
  groupFeaturesByType,
  groupFeaturesByMap,
  type MapGroupItem,
} from "../utils/featureGrouping";
import { isUnrecognizedTextFeature } from "../utils/textValidation";
import { FolderArrowDownIcon, PlusIcon, DocumentDuplicateIcon } from "@heroicons/vue/24/solid";
import { showAlert } from "../composables/useAlert";
import { createFeatureDoubleClickHandler } from "../utils/featureInteraction";
import {
  getContinuousRangeSelection,
} from "../utils/selectionUtils";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  mapPeriods?: MapPeriod[];
  isDevTestCreation?: boolean;
  selectedFeatureId?: string | null;
  multiSelectedFeatureIds?: string[];
  customLabelStyles?: CustomLabelStyle[];
  activeMapId?: string | null;
}>();

const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const labelTextareaRef = ref<HTMLTextAreaElement | null>(null);
const featureToEdit = ref<Feature | undefined>(undefined);
const editDraft = ref<FeatureEditSubmitPayload>({
  name: "",
  wordType: "city",
});

function resizeLabelTextarea() {
  const el = labelTextareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

const areAllMapsSelected = computed(() => {
  if (!props.mapPeriods || props.mapPeriods.length === 0) return false;
  const selected = editDraft.value.selectedMapIds ?? [];
  return props.mapPeriods.every((p: { id: any; }) => selected.includes(p.id));
});

const hasCustomDate = computed(() => {
  const s = editDraft.value.startYear;
  const e = editDraft.value.endYear;
  const hasStart = s !== null && s !== undefined && (typeof s !== "string" || (s as string).trim() !== "");
  const hasEnd = e !== null && e !== undefined && (typeof e !== "string" || (e as string).trim() !== "");
  return hasStart || hasEnd;
});

function toggleSelectAllMaps() {
  if (!props.mapPeriods || hasCustomDate.value) return;
  if (areAllMapsSelected.value) {
    editDraft.value.selectedMapIds = [];
  } else {
    editDraft.value.selectedMapIds = props.mapPeriods.map((p: { id: any; }) => p.id);
  }
}

let previousFeatureStartYear: number | null = null;

function onFeatureStartYearInput() {
  if (editDraft.value.startYear !== null && editDraft.value.startYear !== undefined) {
    editDraft.value.endYear = syncEndFromStart(
      editDraft.value.startYear,
      editDraft.value.endYear,
      previousFeatureStartYear,
    );
    previousFeatureStartYear = editDraft.value.startYear;
  }
  if (hasCustomDate.value) {
    editDraft.value.selectedMapIds = [];
  }
}

function onFeatureEndYearInput() {
  if (hasCustomDate.value) {
    editDraft.value.selectedMapIds = [];
  }
}

const isTextElement = computed(() => isTextFeature(featureToEdit.value));

const isEditingPoint = computed(() => {
  if (!featureToEdit.value) return false;
  if (isTextElement.value) {
    if (editDraft.value.customLabelStyle) return false;
    const entry = WORD_TYPE_TAXONOMY[editDraft.value.wordType as keyof typeof WORD_TYPE_TAXONOMY];
    return (entry?.mapElementType ?? getMapElementType(featureToEdit.value)) === "point";
  }
  return getMapElementType(featureToEdit.value) === "point";
});

const isEditNameMissing = computed(() => {
  return !editDraft.value.name?.trim();
});

const editModalNameText = computed(() => {
  return editDraft.value.name?.trim() || "Élément sans nom";
});

const editModalTypeLabel = computed(() => {
  if (isTextElement.value) return "du texte";
  if (isEditingPoint.value) return "du point";
  const elementType = featureToEdit.value
    ? getMapElementType(featureToEdit.value)
    : undefined;
  if (elementType === "image") return "de l'image";
  return "de la forme";
});

const isTextSizeOverMax = computed(() => {
  const num = Number(editDraft.value.textSizePx);
  return Number.isFinite(num) && num > MAX_TEXT_SIZE_PX;
});

const isPreviewClamped = computed(() => {
  if (!isTextElement.value) return false;
  const rawSize = Number(editDraft.value.textSizePx);
  const textContent = editDraft.value.labelText || editDraft.value.name || "";
  return (
    (Number.isFinite(rawSize) && rawSize > MAX_PREVIEW_FONT_SIZE_PX) ||
    textContent.length > 24
  );
});

function onTextSizeChange() {
  editDraft.value.textSizePx =
    normalizeTextSizePx(editDraft.value.textSizePx) ?? defaultTextSizePx.value;
}

const editTextStyle = computed<CSSProperties>(() => {
  if (!isTextElement.value) return {};
  const selection = editDraft.value.labelStyleSelection ?? "";
  const style = selection.startsWith("custom:")
    ? availableCustomLabelStyles.value.find(
        (item: CustomLabelStyle) => item.id === selection.slice("custom:".length),
      ) ?? editDraft.value.customLabelStyle
    : editDraft.value.customLabelStyle;

  if (style) {
    return getLabelStylePreviewCss(style, { limitSize: true, maxPx: 18 });
  }
  const preview = getWordTypePreviewStyle(
    editDraft.value.wordType,
    isEditingPoint.value
      ? editDraft.value.textColorHex ?? editDraft.value.colorHex
      : editDraft.value.colorHex,
    normalizeTextSizePx(editDraft.value.textSizePx),
  );
  return {
    ...preview,
    fontWeight: "bold",
    fontSize: `${Math.min(parseInt(preview.fontSize, 10) || 14, MAX_PREVIEW_FONT_SIZE_PX)}px`,
  };
});

watch(
  () => [editDraft.value.name, editDraft.value.labelText, editTextStyle.value],
  async () => {
    await nextTick();
    resizeLabelTextarea();
  },
);

const defaultTextSizePx = computed(() =>
  getDefaultTextSizePx(editDraft.value.wordType),
);

const hasGeometryControls = computed(() => {
  if (!featureToEdit.value) return false;
  return isEditingPoint.value || !isTextElement.value;
});

const geometrySectionTitle = computed(() => {
  return isEditingPoint.value ? "Réglages du point" : "Réglages de la forme";
});

const geometrySectionHint = computed(() => {
  if (isEditingPoint.value && isTextElement.value) {
    return "Symbole associé au texte";
  }
  return isEditingPoint.value
    ? "Symbole sur la carte"
    : "Zone, polygone ou ligne";
});

const pointPreviewFillColor = computed(() => {
  return editDraft.value.colorHex || "#000000";
});

const pointPreviewFillOpacity = computed(() => {
  return normalizeOpacity(editDraft.value.fillOpacity) ?? 0.5;
});

const pointPreviewStrokeColor = computed(() => {
  return editDraft.value.strokeColorHex || editDraft.value.colorHex || "#000000";
});

const pointPreviewStrokeOpacity = computed(() => {
  return normalizeOpacity(editDraft.value.strokeOpacity) ?? 1;
});

const pointPreviewStrokeWidth = computed(() => {
  return normalizeStrokeWidth(editDraft.value.strokeWidth) ?? 1;
});

const deleteMapDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const mapToDeleteId = ref<string | null>(null);
const mapToDeleteTitle = ref<string>("");
const isDeletingMap = ref(false);

const isDeletingFeature = ref(false);

const selectMapValidationDialogRef = ref<HTMLDialogElement | undefined>(undefined);

const activeGroupType = ref<FeatureVisibilityGroupType | undefined>(undefined);

const isEditing = ref(false);

const emit = defineEmits([
  "toggle-feature",
  "open-add-image-feature-dialog",
  "save-map",
  "delete-feature",
  "delete-map",
  "add-map",
  "duplicate-map",
  "update-feature",
  "validate-texts",
  "select-feature",
  "select-features",
  "select-map",
  "edit-map",
  "save-label-styles",
]);

const labelStyleManagerRef = ref<InstanceType<typeof CustomLabelStyleManager> | null>(null);

const localCustomStyles = ref<CustomLabelStyle[]>([]);

watch(
  () => props.customLabelStyles,
  (styles: CustomLabelStyle[] | undefined) => {
    if (styles) {
      localCustomStyles.value = [...styles];
    }
  },
  { immediate: true },
);

const availableCustomLabelStyles = computed(() => {
  return localCustomStyles.value.length > 0
    ? localCustomStyles.value
    : props.customLabelStyles ?? [];
});

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  const previousIds = new Set(localCustomStyles.value.map((s: LabelStyle) => s.id));
  localCustomStyles.value = [...styles];

  // If a new style was created and saved, automatically select it for the current element
  const newlyCreatedStyle = styles.find((s) => !previousIds.has(s.id));
  if (newlyCreatedStyle) {
    editDraft.value.labelStyleSelection = `custom:${newlyCreatedStyle.id}`;
    editDraft.value.customLabelStyleId = newlyCreatedStyle.id;
    editDraft.value.customLabelStyle = newlyCreatedStyle;
    editDraft.value.colorHex = newlyCreatedStyle.color;
    const baseText = editDraft.value.labelText || editDraft.value.name || "";
    editDraft.value.labelText =
      newlyCreatedStyle.textTransform === "uppercase" ? baseText.toUpperCase() : baseText;
  } else if (editDraft.value.customLabelStyleId) {
    const updated = styles.find((s) => s.id === editDraft.value.customLabelStyleId);
    if (updated) {
      editDraft.value.customLabelStyle = updated;
      editDraft.value.colorHex = updated.color;
      if (updated.textTransform === "uppercase" && editDraft.value.labelText) {
        editDraft.value.labelText = editDraft.value.labelText.toUpperCase();
      }
    }
  }
  emit("save-label-styles", styles);
}

function onNameInput() {
  if (!isTextElement.value) return;
  const baseText = editDraft.value.name || "";
  if (editDraft.value.customLabelStyle) {
    editDraft.value.labelText =
      editDraft.value.customLabelStyle.textTransform === "uppercase"
        ? baseText.toUpperCase()
        : baseText;
  } else {
    editDraft.value.labelText = formatWordText(baseText, editDraft.value.wordType);
  }
}

function onLabelStyleSelectionChange() {
  const selection = editDraft.value.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const style = availableCustomLabelStyles.value.find(
      (item: CustomLabelStyle) => item.id === selection.slice("custom:".length),
    );
    if (!style) return;
    editDraft.value.customLabelStyleId = style.id;
    editDraft.value.customLabelStyle = style;
    editDraft.value.colorHex = style.color;
    const baseText = editDraft.value.labelText || editDraft.value.name || "";
    editDraft.value.labelText =
      style.textTransform === "uppercase" ? baseText.toUpperCase() : baseText;
    return;
  }
  editDraft.value.customLabelStyleId = undefined;
  editDraft.value.customLabelStyle = undefined;
  const wordType = selection;
  if (Object.prototype.hasOwnProperty.call(WORD_TYPE_TAXONOMY, wordType)) {
    editDraft.value.wordType = wordType as keyof typeof WORD_TYPE_TAXONOMY;
  }
  const originalColorHex = featureToEdit.value
    ? rgbToHex(featureToEdit.value.properties.colorRgb)
    : undefined;
  editDraft.value.colorHex = originalColorHex ?? "#000000";
  editDraft.value.textColorHex =
    (featureToEdit.value
      ? rgbToHex(featureToEdit.value.properties.textColorRgb)
      : undefined) ?? editDraft.value.colorHex;
  editDraft.value.textSizePx = defaultTextSizePx.value;

  const baseText = editDraft.value.labelText || editDraft.value.name || "";
  editDraft.value.labelText = formatWordText(baseText, editDraft.value.wordType);
}

watch(
  () => props.selectedFeatureId,
  async (newId: string | null | undefined) => {
    if (!newId) return;

    const feature = props.features.find(
      (item: Feature) => String(item.id) === newId,
    );
    if (!feature) return;

    const group = featureGroups.value.find((item: FeatureVisibilityGroup) =>
      item.features.some((groupFeature: Feature) => String(groupFeature.id) === newId),
    );
    if (!group) return;

    activeGroupType.value = group.type;
    await nextTick();

    const featMapId = getFeatureMapId(feature);
    const mapGroup = groupFeaturesByMap(group.features, props.mapPeriods).find(
      (item: MapGroupItem) => String(item.id ?? "") === String(featMapId ?? ""),
    );
    if (mapGroup) {
      collapsedMaps.value[`${group.type}_${mapGroup.id ?? "general"}`] = false;
    }

    await nextTick();
    requestAnimationFrame(() => {
      const el = Array.from(
        document.querySelectorAll<HTMLElement>("[data-feature-item-id]"),
      ).find((item) => String(item.dataset.featureItemId) === String(newId));
      el?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    });
  },
);

function openMapSelectionOrValidate() {
  if (validationFeaturesByMap.value.length > 1) {
    selectMapValidationDialogRef.value?.showModal?.();
  } else {
    emit("validate-texts", validationFeaturesByMap.value[0]?.id ?? null);
  }
}

function confirmMapValidation(mapId: string | null) {
  selectMapValidationDialogRef.value?.close?.();
  emit("validate-texts", mapId);
}

const collapsedMaps = ref<Record<string, boolean>>({});

function getMapCollapseKey(mapId: string | null): string {
  return `${activeGroup.value?.type || "default"}_${mapId ?? "general"}`;
}

function isMapCollapsed(mapId: string | null): boolean {
  return !!collapsedMaps.value[getMapCollapseKey(mapId)];
}

function toggleMapCollapse(mapId: string | null) {
  const key = getMapCollapseKey(mapId);
  collapsedMaps.value[key] = !collapsedMaps.value[key];
}

const groupIcons: Record<FeatureVisibilityGroupType, Component> = {
  point: ChatBubbleLeftEllipsisIcon,
  zone: MapIcon,
  shape: Square2StackIcon,
  drawing: PencilSquareIcon,
  image: PhotoIcon,
};

const featureGroups = computed(() => groupFeaturesByType(props.features));

const activeGroup = computed(() => {
  if (!activeGroupType.value) return featureGroups.value[0] ?? undefined;

  return (
    featureGroups.value.find((group: FeatureVisibilityGroup) => group.type === activeGroupType.value) ??
    featureGroups.value[0] ??
    undefined
  );
});

const isAnyVisible = computed(() => {
  if (!activeGroup.value || activeGroup.value.features.length === 0)
    return false;
  return activeGroup.value.features.some(
    (feature: Feature) => props.featureVisibility.get(feature.id) !== false,
  );
});

const featuresByMap = computed((): MapGroupItem[] => {
  if (!activeGroup.value) return [];
  return groupFeaturesByMap(activeGroup.value.features, props.mapPeriods);
});

const validationFeaturesByMap = computed(() =>
  groupFeaturesByMap(
    props.features.filter((feature: Feature) => isUnrecognizedTextFeature(feature)),
    props.mapPeriods,
  ),
);

function toggleMapGroup(mapId: string | null, visible: boolean) {
  const mapGroup = featuresByMap.value.find((g: MapGroupItem) => g.id === mapId);
  if (mapGroup) {
    mapGroup.features.forEach((feature: Feature) => {
      emit("toggle-feature", feature.id, visible);
    });
  }
}

function isMapGroupAnyVisible(mapId: string | null) {
  const mapGroup = featuresByMap.value.find((g: MapGroupItem) => g.id === mapId);
  if (!mapGroup || mapGroup.features.length === 0) return false;
  return mapGroup.features.some(
    (feature: Feature) => props.featureVisibility.get(feature.id) !== false,
  );
}

function toggleActiveGroup(visible: boolean) {
  if (!activeGroup.value) return;
  activeGroup.value.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

watch(
  featureGroups,
  (groups: FeatureVisibilityGroup[]) => {
    if (groups.length === 0) {
      activeGroupType.value = undefined;
      return;
    }

    const hasActiveGroup = groups.some(
      (group: FeatureVisibilityGroup) => group.type === activeGroupType.value,
    );

    if (!hasActiveGroup) {
      activeGroupType.value = groups[0].type;
    }
  },
  { immediate: true },
);

function getGroupIcon(type: FeatureVisibilityGroupType): Component {
  return groupIcons[type];
}

async function showEditFeatureDialog(feature: Feature) {
  const state = prepareFeatureForEdit(feature);
  featureToEdit.value = state.feature;
  editDraft.value = state.draft;
  previousFeatureStartYear = editDraft.value.startYear ?? null;

  await nextTick();
  editFeatureDialogRef.value?.showModal();
  await nextTick();
  resizeLabelTextarea();
}

const lastSelectedAnchorId = ref<string | null>(props.selectedFeatureId ?? null);

watch(
  () => props.selectedFeatureId,
  (newId) => {
    if (newId) lastSelectedAnchorId.value = String(newId);
  },
);

const visibleListFeatureIds = computed(() =>
  featuresByMap.value.flatMap((g: MapGroupItem) => g.features).map((f: Feature) => String(f.id)),
);

function isFeatureSelected(id: string | number | undefined): boolean {
  if (id == null) return false;
  const strId = String(id);
  if (props.selectedFeatureId && String(props.selectedFeatureId) === strId) return true;
  if (
    props.multiSelectedFeatureIds &&
    props.multiSelectedFeatureIds.some((i) => String(i) === strId)
  )
    return true;
  return false;
}

const { handleClick: onFeatureItemClick, handleDblClick: onFeatureItemDblClick } =
  createFeatureDoubleClickHandler<Feature>({
    onSelect: (feature: Feature, event?: unknown) => {
      if (feature.id == null) return;
      const featureId = String(feature.id);
      const mouseEv = event as MouseEvent | undefined;
      const isCtrl = Boolean(mouseEv?.ctrlKey || mouseEv?.metaKey);
      const isShift = Boolean(mouseEv?.shiftKey);

      if (isCtrl) {
        const currentList = props.multiSelectedFeatureIds ?? [];
        const next = new Set<string>(currentList);
        if (props.selectedFeatureId) {
          next.add(props.selectedFeatureId);
        } else if (lastSelectedAnchorId.value) {
          next.add(lastSelectedAnchorId.value);
        }
        if (next.has(featureId)) {
          next.delete(featureId);
        } else {
          next.add(featureId);
        }
        lastSelectedAnchorId.value = featureId;
        emit("select-feature", null);
        emit("select-features", Array.from(next));
        return;
      }

      if (isShift) {
        const range = getContinuousRangeSelection(
          visibleListFeatureIds.value,
          lastSelectedAnchorId.value,
          featureId,
        );
        if (range.length > 0) {
          lastSelectedAnchorId.value = lastSelectedAnchorId.value || featureId;
          emit("select-feature", null);
          emit("select-features", range);
          return;
        }
      }

      lastSelectedAnchorId.value = featureId;
      emit("select-features", []);
      emit("select-feature", featureId);
    },
    onEdit: (feature: Feature) => {
      if (feature.id != null) {
        lastSelectedAnchorId.value = String(feature.id);
        emit("select-feature", String(feature.id));
      }
      showEditFeatureDialog(feature);
    },
    getId: (feature: Feature) => feature.id,
  });

async function onEditFeature() {
  if (!featureToEdit.value) return;
  isEditing.value = true;

  const updatedFeature = coerceEditedFeature(featureToEdit.value, {
    ...editDraft.value,
  });

  const allUpdated = createFeaturesForSelectedMaps(
    updatedFeature,
    editDraft.value.selectedMapIds,
  );

  featureToEdit.value = updatedFeature;

  emit(
    "update-feature",
    (allUpdated.length === 1 ? allUpdated[0] : allUpdated) as any,
    {
      onSuccess: () => {
        showAlert("success", "Élément mis à jour !");
      },
      onError: (message: string) => {
        showAlert("error", message);
      },
    },
  );

  isEditing.value = false;
  editFeatureDialogRef.value?.close();
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

function showDeleteMapDialog(mapId: string, mapTitle: string) {
  mapToDeleteId.value = mapId;
  mapToDeleteTitle.value = mapTitle;
  deleteMapDialogRef.value?.showModal();
}

async function onDeleteMap() {
  if (!mapToDeleteId.value) return;
  isDeletingMap.value = true;
  emit("delete-map", mapToDeleteId.value, {
    onSuccess: () => {
      showAlert("success", "Carte supprimée avec succès !");
      isDeletingMap.value = false;
      deleteMapDialogRef.value?.close();
    },
    onError: (message: string) => {
      showAlert("error", message || "Erreur lors de la suppression de la carte.");
      isDeletingMap.value = false;
    },
  });
}

const deleteFeatureDialogRef = ref<InstanceType<typeof DeleteFeatureDialog> | null>(null);

function showDeleteFeatureDialog(featureOrFeatures: Feature | Feature[]) {
  deleteFeatureDialogRef.value?.open(featureOrFeatures);
}

async function onDeleteFeaturesConfirmed(idsToDelete: string[]) {
  if (idsToDelete.length === 0) return;
  isDeletingFeature.value = true;
  emit("delete-feature", idsToDelete.length === 1 ? idsToDelete[0] : idsToDelete, {
    onSuccess: () => {
      showAlert(
        "success",
        idsToDelete.length > 1
          ? `${idsToDelete.length} éléments supprimés avec succès !`
          : "Élément supprimé avec succès !",
      );
      isDeletingFeature.value = false;
      deleteFeatureDialogRef.value?.close();
    },
    onError: (message: string) => {
      showAlert("error", message || "Erreur lors de la suppression de l'élément.");
      isDeletingFeature.value = false;
    },
  });
}

async function onRemoveFromMapsConfirmed(payload: { featureIds: string[]; mapIdsToRemove: string[] }) {
  const { featureIds, mapIdsToRemove } = payload;
  if (featureIds.length === 0 || mapIdsToRemove.length === 0) return;

  const removeSet = new Set(mapIdsToRemove.map(String));
  const feats = props.features.filter((f) => featureIds.includes(String(f.id)));
  if (feats.length === 0) return;

  isDeletingFeature.value = true;
  const updatedList: Feature[] = [];

  for (const feat of feats) {
    const existingIds = getFeatureMapIds(feat);
    const nextMapIds = existingIds.filter((id) => !removeSet.has(String(id)));
    const newMainMapId = nextMapIds.length > 0 ? nextMapIds[0] : null;

    const updated: Feature = {
      ...feat,
      mapId: newMainMapId,
      mapIds: nextMapIds,
      properties: {
        ...feat.properties,
        mapId: newMainMapId,
        mapIds: nextMapIds,
      },
    };
    updatedList.push(updated);
  }

  emit(
    "update-feature",
    (updatedList.length === 1 ? updatedList[0] : updatedList) as any,
    {
      onSuccess: () => {
        showAlert(
          "success",
          updatedList.length > 1
            ? `${updatedList.length} éléments retirés avec succès !`
            : "Élément retiré de la carte avec succès !",
        );
        isDeletingFeature.value = false;
        deleteFeatureDialogRef.value?.close();
      },
      onError: (message?: string) => {
        showAlert("error", message || "Erreur lors du retrait de l'élément.");
        isDeletingFeature.value = false;
      },
    },
  );
}

defineExpose({
  showEditFeatureDialog,
  showDeleteFeatureDialog,
  isMapCollapsed,
  toggleMapCollapse,
});
</script>