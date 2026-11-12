<#import "template.ftl" as layout>

<@layout.registrationLayout displayMessage=true; section>

    <#if section = "header">

        <div class="atlas-brand">
            <div class="atlas-logo">Atlas</div>
        </div>

    <#elseif section = "form">

        <h1 id="kc-page-title">
            ${msg("atlasResetPasswordTitle")}
        </h1>

        <p class="atlas-description">
            ${msg("atlasResetPasswordDescription")}
        </p>

        <form
            id="kc-reset-password-form"
            action="${url.loginAction}"
            method="post">

            <div class="atlas-field">
                <label for="username">
                    ${msg("usernameOrEmail")}
                </label>

                <input
                    id="username"
                    name="username"
                    type="text"
                    autofocus
                    autocomplete="username"
                />
            </div>

            <button
                id="kc-login"
                type="submit">
                ${msg("doSubmit")}
            </button>

        </form>

        <a
            class="atlas-back"
            href="${url.loginUrl}">
            ${msg("atlasBackToLogin")}
        </a>

    </#if>

</@layout.registrationLayout>