/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 *  contributor license agreements.  The ASF licenses this file to You
 * under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.  For additional information regarding
 * copyright in this work, please see the NOTICE file in the top level
 * directory of this distribution.
 */

package org.apache.roller.weblogger.ui.struts2.editor;

import java.util.Collections;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.roller.weblogger.WebloggerException;
import org.apache.roller.weblogger.config.WebloggerConfig;
import org.apache.roller.weblogger.business.WebloggerFactory;
import org.apache.roller.weblogger.business.UserManager;
import org.apache.roller.weblogger.pojos.User;
import org.apache.roller.weblogger.pojos.WeblogPermission;
import org.apache.roller.weblogger.ui.struts2.util.UIAction;
import org.apache.roller.weblogger.util.MailUtil;
import org.apache.struts2.convention.annotation.AllowedMethods;

/**
 * Allows website admin to invite new members to website.
 *
 * TODO: handle 'disabled' result
 */
// TODO: make this work @AllowedMethods({"execute","save","cancel"})
public class MembersInvite extends UIAction {

    private static Log log = LogFactory.getLog(MembersInvite.class);

    // user being invited
    private String userName = null;

    // permissions being given to user
    private String permissionString = null;

    public MembersInvite() {
        this.actionName = "invite";
        this.desiredMenu = "editor";
        this.pageTitle = "inviteMember.title";
    }

    @Override
    public String execute() {
        if (!isGroupBloggingEnabled()) {
            addError("inviteMember.disabled");
            return SUCCESS;
        }
        log.debug("Showing weblog invitation form");
        return INPUT;
    }

    /**
     * Save the new invitation and notify the user.
     */
    public String save() {
        if (!isGroupBloggingEnabled()) {
            addError("inviteMember.disabled");
            return SUCCESS;
        }
        log.debug("Attempting to process weblog invitation");
        try {
            processInvitation();
        } catch (WebloggerException ex) {
            log.error("Error processing invitation", ex);
            addError("Error processing invitation");
        }
        return hasActionErrors() ? INPUT : SUCCESS;
    }

    private void processInvitation() throws WebloggerException {
        UserManager umgr = WebloggerFactory.getWeblogger().getUserManager();
        User user = getUser(umgr);
        if (user == null) {
            addError("inviteMember.error.userNotFound");
            return;
        }
        if (hasExistingPermission(umgr, user)) {
            return;
        }
        grantPermission(umgr, user);
        sendInvitation();
    }

    private boolean isGroupBloggingEnabled() {
        return WebloggerConfig.getBooleanProperty("groupblogging.enabled");
    }

    private User getUser(UserManager umgr) {
        try {
            return umgr.getUserByUserName(getUserName());
        } catch (WebloggerException ex) {
            log.error("Error looking up user by id - " + getUserName(), ex);
            addError("Error looking up invitee");
            return null;
        }
    }

    private boolean hasExistingPermission(UserManager umgr, User user) {
        try {
            WeblogPermission perm = umgr.getWeblogPermissionIncludingPending(getActionWeblog(), user);
            if (perm != null && perm.isPending()) {
                addError("inviteMember.error.userAlreadyInvited");
                return true;
            } else if (perm != null) {
                addError("inviteMember.error.userAlreadyMember");
                return true;
            }
        } catch (WebloggerException ex) {
            log.error("Error looking up permissions for weblog - " + getActionWeblog().getHandle(), ex);
            addError("Error checking existing permissions");
        }
        return hasActionErrors();
    }

    private void grantPermission(UserManager umgr, User user) throws WebloggerException {
        umgr.grantWeblogPermissionPending(getActionWeblog(), user, Collections.singletonList(getPermissionString()));
        WebloggerFactory.getWeblogger().flush();
        addMessage("inviteMember.userInvited");
    }

    private void sendInvitation() {
        if (MailUtil.isMailConfigured()) {
            try {
                MailUtil.sendWeblogInvitation(getActionWeblog(), getUser(WebloggerFactory.getWeblogger().getUserManager()));
            } catch (WebloggerException e) {
                // TODO: this should be an error except that struts2 misbehaves
                // when we chain this action to the next one thinking that an error
                // means that validation broke during the chain
                addMessage("error.untranslated", e.getMessage());
            }
        }
        log.debug("Invitation successfully recorded");
    }

    /**
     * Cancel.
     * 
     * @return the string
     */
    @Override
    public String cancel() {
        return CANCEL;
    }

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userId) {
        this.userName = userId;
    }

    public String getPermissionString() {
        return permissionString;
    }

    public void setPermissionString(String permission) {
        this.permissionString = permission;
    }
}