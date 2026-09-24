<#import "template.ftl" as layout>

<@layout.registrationLayout displayMessage=true; section>

    <#if section = "header">

        <div class="atlas-brand">
            <div class="atlas-logo">Atlas</div>
        </div>

    <#elseif section = "form">

        <form id="kc-form-login"
              action="${url.loginAction}"
              method="post">

            <div class="atlas-field">
                <label for="username">
                    ${msg("usernameOrEmail")}
                </label>

                <input
                    id="username"
                    name="username"
                    value="${(login.username!'')}"
                    type="text"
                    autofocus
                    autocomplete="username"
                />
            </div>

            <div class="atlas-field">
                <label for="password">
                    ${msg("password")}
                </label>

                <input
                    id="password"
                    name="password"
                    type="password"
                    autocomplete="current-password"
                />
            </div>

            <#if realm.resetPasswordAllowed>
                <div class="atlas-forgot">
                    <a href="${url.loginResetCredentialsUrl}">
                        ${msg("doForgotPassword")}
                    </a>
                </div>
            </#if>

            <button
                id="kc-login"
                type="submit">
                ${msg("doLogIn")}
            </button>

        </form>

        <a
            class="atlas-back"
            href="${client.baseUrl!'http://localhost:3000'}">
            ← Back to Atlas
        </a>

    </#if>

</@layout.registrationLayout>