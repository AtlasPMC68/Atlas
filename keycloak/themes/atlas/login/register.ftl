<#import "template.ftl" as layout>

<@layout.registrationLayout displayMessage=true; section>

    <#if section = "header">

        <div class="atlas-brand">
            <div class="atlas-logo">Atlas</div>
        </div>

    <#elseif section = "form">

        <h1 id="kc-page-title">
            Create your account
        </h1>

        <form
            id="kc-register-form"
            action="${url.registrationAction}"
            method="post">

            <div class="atlas-field">
                <label for="username">
                    ${msg("username")}
                </label>

                <input
                    id="username"
                    name="username"
                    value="${(register.formData.username!'')}"
                    type="text"
                    autofocus
                    autocomplete="username"
                />
            </div>

            <div class="atlas-field">
                <label for="email">
                    ${msg("email")}
                </label>

                <input
                    id="email"
                    name="email"
                    value="${(register.formData.email!'')}"
                    type="email"
                    autocomplete="email"
                />
            </div>

            <div class="atlas-field">
                <label for="firstName">
                    ${msg("firstName")}
                </label>

                <input
                    id="firstName"
                    name="firstName"
                    value="${(register.formData.firstName!'')}"
                    type="text"
                    autocomplete="given-name"
                />
            </div>

            <div class="atlas-field">
                <label for="lastName">
                    ${msg("lastName")}
                </label>

                <input
                    id="lastName"
                    name="lastName"
                    value="${(register.formData.lastName!'')}"
                    type="text"
                    autocomplete="family-name"
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
                    autocomplete="new-password"
                />
            </div>

            <div class="atlas-field">
                <label for="password-confirm">
                    ${msg("passwordConfirm")}
                </label>

                <input
                    id="password-confirm"
                    name="password-confirm"
                    type="password"
                    autocomplete="new-password"
                />
            </div>

            <button
                id="kc-login"
                type="submit">
                ${msg("doRegister")}
            </button>

        </form>

        <a
            class="atlas-back"
            href="${url.loginUrl}">
            ← Back to login
        </a>

    </#if>

</@layout.registrationLayout>